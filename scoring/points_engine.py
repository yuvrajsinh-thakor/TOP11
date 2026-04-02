from decimal import Decimal
from django.db import transaction
from .models import PointsRule, PlayerMatchScore, Leaderboard, AuditLog
from contests.models import UserTeam, UserTeamPlayer, ContestEntry, Contest
from matches.models import Match
from payments.models import Transaction
from accounts.models import Wallet
from django.conf import settings
# Add at the top of scoring/points_engine.py
from scoring.broadcast import (
    broadcast_score_update,
    broadcast_all_scores,
    broadcast_leaderboard_update,
    broadcast_match_status,
)


def get_points_rules():
    """
    Load all active points rules from DB into a dict.
    Returns: { 'RUN': Decimal('1'), 'WICKET': Decimal('25'), ... }
    """
    rules = PointsRule.objects.filter(is_active=True)
    return {rule.event_code: rule.points for rule in rules}


def calculate_player_points(stats, rules):
    """
    Calculate raw fantasy points for one player from their match stats.

    stats: dict with keys like runs_scored, wickets_taken, catches etc.
    rules: dict from get_points_rules()

    Returns: (total_points, breakdown_dict)
    """
    breakdown = {}
    total = Decimal('0')

    runs = stats.get('runs_scored', 0)
    fours = stats.get('fours', 0)
    sixes = stats.get('sixes', 0)
    is_out = stats.get('is_out', False)
    wickets = stats.get('wickets_taken', 0)
    maidens = stats.get('maiden_overs', 0)
    catches = stats.get('catches', 0)
    stumpings = stats.get('stumpings', 0)
    run_outs_direct = stats.get('run_outs_direct', 0)
    run_outs_indirect = stats.get('run_outs_indirect', 0)

    # --- Batting points ---
    if 'RUN' in rules and runs > 0:
        pts = rules['RUN'] * runs
        breakdown['RUN'] = float(pts)
        total += pts

    if 'BOUNDARY' in rules and fours > 0:
        pts = rules['BOUNDARY'] * fours
        breakdown['BOUNDARY'] = float(pts)
        total += pts

    if 'SIX' in rules and sixes > 0:
        pts = rules['SIX'] * sixes
        breakdown['SIX'] = float(pts)
        total += pts

    if 'DUCK' in rules and is_out and runs == 0:
        pts = rules['DUCK']
        breakdown['DUCK'] = float(pts)
        total += pts

    # Batting milestones
    if runs >= 100 and 'MILESTONE_100' in rules:
        pts = rules['MILESTONE_100']
        breakdown['MILESTONE_100'] = float(pts)
        total += pts
    elif runs >= 50 and 'MILESTONE_50' in rules:
        pts = rules['MILESTONE_50']
        breakdown['MILESTONE_50'] = float(pts)
        total += pts
    elif runs >= 30 and 'MILESTONE_30' in rules:
        pts = rules['MILESTONE_30']
        breakdown['MILESTONE_30'] = float(pts)
        total += pts

    # --- Bowling points ---
    if 'WICKET' in rules and wickets > 0:
        pts = rules['WICKET'] * wickets
        breakdown['WICKET'] = float(pts)
        total += pts

    if 'MAIDEN' in rules and maidens > 0:
        pts = rules['MAIDEN'] * maidens
        breakdown['MAIDEN'] = float(pts)
        total += pts

    # Bowling bonuses
    if wickets >= 5 and 'BONUS_5W' in rules:
        pts = rules['BONUS_5W']
        breakdown['BONUS_5W'] = float(pts)
        total += pts
    elif wickets >= 3 and 'BONUS_3W' in rules:
        pts = rules['BONUS_3W']
        breakdown['BONUS_3W'] = float(pts)
        total += pts

    # --- Fielding points ---
    if 'CATCH' in rules and catches > 0:
        pts = rules['CATCH'] * catches
        breakdown['CATCH'] = float(pts)
        total += pts

    if 'STUMPING' in rules and stumpings > 0:
        pts = rules['STUMPING'] * stumpings
        breakdown['STUMPING'] = float(pts)
        total += pts

    if 'RUNOUT_DIRECT' in rules and run_outs_direct > 0:
        pts = rules['RUNOUT_DIRECT'] * run_outs_direct
        breakdown['RUNOUT_DIRECT'] = float(pts)
        total += pts

    if 'RUNOUT_THROW' in rules and run_outs_indirect > 0:
        pts = rules['RUNOUT_THROW'] * run_outs_indirect
        breakdown['RUNOUT_THROW'] = float(pts)
        total += pts

    return total, breakdown


@transaction.atomic
def save_player_score(match, player, stats, rules):
    """
    Calculate and save/update a player's fantasy points for a match.
    Returns the PlayerMatchScore object.
    """
    total_points, breakdown = calculate_player_points(stats, rules)

    score, _ = PlayerMatchScore.objects.update_or_create(
        match=match,
        player=player,
        defaults={
            'runs_scored': stats.get('runs_scored', 0),
            'balls_faced': stats.get('balls_faced', 0),
            'fours': stats.get('fours', 0),
            'sixes': stats.get('sixes', 0),
            'is_out': stats.get('is_out', False),
            'wickets_taken': stats.get('wickets_taken', 0),
            'runs_conceded': stats.get('runs_conceded', 0),
            'maiden_overs': stats.get('maiden_overs', 0),
            'catches': stats.get('catches', 0),
            'stumpings': stats.get('stumpings', 0),
            'run_outs_direct': stats.get('run_outs_direct', 0),
            'run_outs_indirect': stats.get('run_outs_indirect', 0),
            'total_fantasy_points': total_points,
            'points_breakdown': breakdown,
        }
    )


    # Broadcast to all WebSocket clients watching this match
    try:
        broadcast_score_update(
            match_id=str(match.id),
            player_id=str(player.id),
            player_name=player.name,
            total_points=float(total_points),
            breakdown=breakdown,
        )
    except Exception:
        pass  # Never let broadcast failure break score saving
    return score


@transaction.atomic
def update_all_team_points(match):
    """
    After updating player scores, recalculate total points
    for every UserTeam in this match.
    Applies captain (2x) and vice-captain (1.5x) multipliers.
    """
    # Get all player scores for this match in one query
    player_scores = {
        str(ps.player_id): ps.total_fantasy_points
        for ps in PlayerMatchScore.objects.filter(match=match)
    }

    # Get all teams for this match
    teams = UserTeam.objects.filter(
        match=match
    ).prefetch_related('team_players')

    for team in teams:
        total = Decimal('0')
        for tp in team.team_players.all():
            raw_pts = player_scores.get(str(tp.player_id), Decimal('0'))
            final_pts = raw_pts * tp.multiplier
            tp.raw_points = raw_pts
            tp.final_points = final_pts
            tp.save()
            total += final_pts

        team.total_points = total
        team.save()


@transaction.atomic
def rebuild_leaderboard(contest):
    """
    Rebuild the leaderboard for a contest based on current team points.
    Assigns ranks and calculates prize amounts.
    """
    # Get all entries sorted by team points descending
    entries = ContestEntry.objects.filter(
        contest=contest
    ).select_related('user', 'team').order_by(
        '-team__total_points', 'joined_at'  # tiebreak: earlier entry wins
    )

    # Delete existing leaderboard for this contest
    Leaderboard.objects.filter(contest=contest).delete()

    prize_distribution = contest.prize_distribution
    leaderboard_entries = []

    for rank, entry in enumerate(entries, start=1):
        # Find prize for this rank
        prize = 0
        for tier in prize_distribution:
            if tier['rank_from'] <= rank <= tier['rank_to']:
                prize = tier['prize']
                break

        leaderboard_entries.append(Leaderboard(
            contest=contest,
            contest_entry=entry,
            user=entry.user,
            team=entry.team,
            rank=rank,
            total_points=entry.team.total_points,
            prize_amount=prize,
        ))

    Leaderboard.objects.bulk_create(leaderboard_entries)
    # Broadcast leaderboard update
    try:
        lb_data = [{
            'rank': e.rank,
            'user': e.user.full_name or e.user.email.split('@')[0],
            'team_name': e.team.name,
            'points': float(e.total_points),
            'prize_inr': round(e.prize_amount / 100, 2),
        } for e in leaderboard_entries]

        broadcast_leaderboard_update(
            contest_id=str(contest.id),
            leaderboard_data=lb_data[:50],
            total_entries=contest.current_entries,
        )
    except Exception:
        pass

    return leaderboard_entries


@transaction.atomic
def distribute_prizes(contest):
    """
    After match completes, credit prize winnings to winners' wallets.
    Deducts TDS on large winnings. Only runs once per contest.
    """
    if contest.status == 'completed':
        return {'error': 'Prizes already distributed for this contest.'}

    leaderboard = Leaderboard.objects.filter(
        contest=contest,
        prize_amount__gt=0
    ).select_related('user')

    credited_count = 0
    total_distributed = 0

    for entry in leaderboard:
        contest_entry = ContestEntry.objects.get(
            contest=contest,
            user=entry.user,
            team=entry.team,
        )

        if contest_entry.prize_credited:
            continue

        prize_paise = entry.prize_amount

        # TDS deduction
        tds = 0
        if prize_paise > settings.TOP11_TDS_THRESHOLD * 100:
            tds = int(prize_paise * settings.TOP11_TDS_RATE)

        net_prize = prize_paise - tds

        # Credit to winnings balance
        wallet = entry.user.wallet
        wallet.winnings_balance += net_prize
        wallet.save()

        # Record transaction
        import uuid
        Transaction.objects.create(
            user=entry.user,
            transaction_type='prize_credit',
            status='success',
            amount=net_prize,
            wallet_bucket='winnings',
            description=f'Prize for Rank {entry.rank} in {contest.name}',
            idempotency_key=f'prize_{contest.id}_{entry.user.id}_{entry.team.id}',
        )

        # Record TDS
        if tds > 0:
            Transaction.objects.create(
                user=entry.user,
                transaction_type='tds',
                status='success',
                amount=tds,
                wallet_bucket='winnings',
                description=f'TDS on prize of ₹{prize_paise/100:.2f}',
                idempotency_key=f'tds_prize_{contest.id}_{entry.user.id}',
            )

        # Mark entry as prize credited
        contest_entry.rank = entry.rank
        contest_entry.prize_won = net_prize
        contest_entry.tds_deducted = tds
        contest_entry.is_winner = True
        contest_entry.prize_credited = True
        contest_entry.save()

        credited_count += 1
        total_distributed += net_prize

    # Mark contest as completed
    contest.status = 'completed'
    contest.save()

    return {
        'winners_credited': credited_count,
        'total_distributed_inr': round(total_distributed / 100, 2),
    }


def cancel_contest_and_refund(contest):
    """
    Cancel a contest (min entries not met) and refund all entry fees.
    """
    if contest.current_entries >= contest.min_entries:
        return {'error': 'Contest has enough entries, cannot cancel.'}

    entries = ContestEntry.objects.filter(
        contest=contest
    ).select_related('user')

    refunded = 0
    import uuid
    for entry in entries:
        if entry.entry_fee_paid > 0:
            wallet = entry.user.wallet
            wallet.deposit_balance += entry.entry_fee_paid
            wallet.save()

            Transaction.objects.create(
                user=entry.user,
                transaction_type='refund',
                status='success',
                amount=entry.entry_fee_paid,
                wallet_bucket='deposit',
                description=f'Refund: {contest.name} cancelled',
                idempotency_key=f'cancel_refund_{contest.id}_{entry.user.id}',
            )
            refunded += 1

    contest.status = 'cancelled'
    contest.save()

    return {'refunded_count': refunded, 'contest': contest.name}