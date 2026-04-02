import requests
from django.conf import settings


CRICAPI_BASE = 'https://api.cricapi.com/v1'


def get_match_scorecard(cricapi_match_id):
    """
    Fetch full scorecard for a match from CricAPI.
    Returns parsed player stats or None on error.
    """
    try:
        response = requests.get(
            f'{CRICAPI_BASE}/match_scorecard',
            params={
                'apikey': settings.CRICAPI_KEY,
                'id': cricapi_match_id,
            },
            timeout=10,
        )
        data = response.json()

        if data.get('status') != 'success':
            print(f"CricAPI error: {data.get('reason', 'Unknown error')}")
            return None

        return data.get('data', {})

    except requests.exceptions.RequestException as e:
        print(f"CricAPI network error: {e}")
        return None


def parse_player_stats_from_scorecard(scorecard_data):
    """
    Parse CricAPI scorecard into a flat dict of player stats.
    Returns: { player_name: { runs_scored, wickets_taken, ... } }

    CricAPI scorecard structure:
    scorecard → list of innings → batsmen + bowlers
    """
    player_stats = {}

    if not scorecard_data:
        return player_stats

    scorecard = scorecard_data.get('scorecard', [])

    for innings in scorecard:
        # --- Parse batting ---
        batting = innings.get('batting', [])
        for batter in batting:
            name = batter.get('batsman', {}).get('name', '')
            if not name:
                continue

            if name not in player_stats:
                player_stats[name] = _empty_stats()

            player_stats[name]['runs_scored'] += int(batter.get('r', 0))
            player_stats[name]['balls_faced'] += int(batter.get('b', 0))
            player_stats[name]['fours'] += int(batter.get('4s', 0))
            player_stats[name]['sixes'] += int(batter.get('6s', 0))

            # Check if dismissed
            dismissal = batter.get('dismissal-text', '')
            if dismissal and dismissal.lower() not in ['not out', 'batting', '']:
                player_stats[name]['is_out'] = True

        # --- Parse bowling ---
        bowling = innings.get('bowling', [])
        for bowler in bowling:
            name = bowler.get('bowler', {}).get('name', '')
            if not name:
                continue

            if name not in player_stats:
                player_stats[name] = _empty_stats()

            player_stats[name]['wickets_taken'] += int(bowler.get('w', 0))
            player_stats[name]['runs_conceded'] += int(bowler.get('r', 0))
            player_stats[name]['maiden_overs'] += int(bowler.get('m', 0))

        # --- Parse fielding (catches/stumpings from batting dismissals) ---
        for batter in batting:
            dismissal = batter.get('dismissal-text', '').lower()

            if 'c ' in dismissal and 'b ' in dismissal:
                # Format: "c FielderName b BowlerName"
                parts = dismissal.split(' ')
                if len(parts) >= 2:
                    fielder = batter.get('batsman', {}).get('name', '')
                    # Try to extract fielder name
                    try:
                        c_index = parts.index('c')
                        b_index = parts.index('b')
                        fielder_name = ' '.join(parts[c_index+1:b_index])
                        if fielder_name and fielder_name not in ['&', '']:
                            if fielder_name not in player_stats:
                                player_stats[fielder_name] = _empty_stats()
                            player_stats[fielder_name]['catches'] += 1
                    except (ValueError, IndexError):
                        pass

            elif 'st ' in dismissal:
                # Stumping — credit to wicketkeeper
                parts = dismissal.split(' ')
                try:
                    st_index = parts.index('st')
                    b_index = parts.index('b')
                    keeper_name = ' '.join(parts[st_index+1:b_index])
                    if keeper_name and keeper_name not in ['&', '']:
                        if keeper_name not in player_stats:
                            player_stats[keeper_name] = _empty_stats()
                        player_stats[keeper_name]['stumpings'] += 1
                except (ValueError, IndexError):
                    pass

            elif 'run out' in dismissal:
                # Run out — harder to attribute, skip for now
                pass

    return player_stats


def _empty_stats():
    return {
        'runs_scored': 0,
        'balls_faced': 0,
        'fours': 0,
        'sixes': 0,
        'is_out': False,
        'wickets_taken': 0,
        'runs_conceded': 0,
        'maiden_overs': 0,
        'catches': 0,
        'stumpings': 0,
        'run_outs_direct': 0,
        'run_outs_indirect': 0,
    }


def get_upcoming_matches():
    """Fetch upcoming matches from CricAPI"""
    try:
        response = requests.get(
            f'{CRICAPI_BASE}/matches',
            params={
                'apikey': settings.CRICAPI_KEY,
                'offset': 0,
            },
            timeout=10,
        )
        data = response.json()
        if data.get('status') == 'success':
            return data.get('data', [])
        return []
    except Exception as e:
        print(f"CricAPI error: {e}")
        return []