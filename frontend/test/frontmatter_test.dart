import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/utils/frontmatter.dart';

void main() {
  test('strips a leading frontmatter block', () {
    const page =
        '---\n'
        'title: "Hidden Markov Models"\n'
        'type: concept\n'
        'user_edited: false\n'
        '---\n'
        '\n'
        '## Summary\n';

    expect(stripFrontmatter(page), '## Summary\n');
  });

  test('handles CRLF line endings', () {
    expect(stripFrontmatter('---\r\ntitle: x\r\n---\r\n\r\nBody'), 'Body');
  });

  test('leaves content without frontmatter unchanged', () {
    const text = 'Intro\n\n---\n\nMore';
    expect(stripFrontmatter(text), text);
  });

  test('leaves an unterminated block unchanged', () {
    const text = '---\ntitle: x\nBody';
    expect(stripFrontmatter(text), text);
  });
}
