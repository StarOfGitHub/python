import sys


if __name__  == '__main__':
    source_file, config_file, project_name, position = sys.argv[1:]

    assert position in ('top', 'bottom')

    start_tag = '#--{}--\n'.format(project_name)
    end_tag = '#-/{}--\n'.format(project_name)

    if config_file:
        with open(config_file, 'r') as f:
            config = ''.join(f.readlines())
    else:
        config = ''

    with open(source_file, 'r') as f:
        source_lines = f.readlines()

    if start_tag in source_lines and end_tag not in source_lines:
        raise Exception('Start tag is already in the source file, but does not have end tag')

    if end_tag in source_lines and end_tag not in source_lines:
        raise Exception('End tag is already in the source file, but does not have start tag')

    if start_tag in source_lines and end_tag in source_lines:
        start_tag_pos = source_lines.index(start_tag)
        end_tag_pos = source_lines.index(end_tag)

        before = ''.join(source_lines[:start_tag_pos])
        after = ''.join(source_lines[end_tag_pos+1:])

    else:
        if position == 'bottom':
            before = ''.join(source_lines)
            after = ''
        elif position == 'top':
            before = ''
            after = ''.join(source_lines)

    output = '{}{}{}{}{}'.format(
        before,
        start_tag,
        config,
        end_tag,
        after,
    )

    print(output, end='', flush=True)
