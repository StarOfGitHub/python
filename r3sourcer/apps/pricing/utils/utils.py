def format_timedelta(time_delta, with_seconds=False):
    seconds = time_delta.total_seconds()
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    parts = []

    if hours:
        parts.append('{:g}h'.format(hours))

    if minutes:
        parts.append('{:g}min'.format(minutes))

    if with_seconds and seconds:
        parts.append('{:g}s'.format(seconds))

    return ' '.join(parts)
