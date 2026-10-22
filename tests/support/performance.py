"""Performance policy decisions independent of the benchmark harness."""
import statistics
import math


def calibration_scale(reference, candidate, max_noise):
    for samples in (reference, candidate):
        if len(samples) < 4 or any(not math.isfinite(x) or x <= 0 for x in samples):
            raise ValueError('Calibration requires four finite positive samples')
        if max(samples) / min(samples) - 1 > max_noise:
            raise ValueError('Calibration is inconclusive: host timing noise exceeds policy')
    return statistics.median(reference) / statistics.median(candidate)


def compare_times(baseline, candidate, policy):
    if len(baseline) < 2 or len(candidate) < 2 or any(not math.isfinite(value) or value < 0 for value in baseline + candidate):
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
    if any(type(value) is not int or value < 0 for value in (before, after)):
        raise ValueError('Work comparisons require nonnegative integer counts')
    limit = before * (1 + policy['relative_increase']) + policy['absolute_calls']
    return {'passed': after <= limit, 'baseline': before, 'candidate': after, 'limit': limit}
