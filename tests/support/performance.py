"""Performance policy decisions independent of the benchmark harness."""
import statistics


def compare_times(baseline, candidate, policy):
    if len(baseline) < 2 or len(candidate) < 2 or any(value < 0 for value in baseline + candidate):
        raise ValueError('Timing comparison requires repeated nonnegative samples')
    before, after = statistics.median(baseline), statistics.median(candidate)
    noise = max(max(baseline) - min(baseline), max(candidate) - min(candidate))
    material = max(policy['absolute_ms'], before * policy['relative_increase'])
    limit = max(material, noise * policy['noise_multiplier'])
    delta = after - before
    inconclusive = material < delta <= limit
    return {'passed': delta <= material, 'status': 'inconclusive' if inconclusive else 'failed' if delta > limit else 'passed',
            'baseline_ms': before, 'candidate_ms': after, 'delta_ms': delta,
            'noise_ms': noise, 'limit_ms': limit, 'material_limit_ms': material}


def compare_work(before, after, policy):
    limit = before * (1 + policy['relative_increase']) + policy['absolute_calls']
    return {'passed': after <= limit, 'baseline': before, 'candidate': after, 'limit': limit}
