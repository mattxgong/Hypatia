import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/models/wiki_page.dart';
import 'package:frontend/utils/wiki_markdown.dart';

const _pages = [
  WikiPageSummary(
    id: '1',
    path: 'pages/concept/log-linear-models.md',
    title: 'Log-Linear Models',
    category: WikiCategory.concept,
  ),
];

void main() {
  group('resolveWikiLinks', () {
    test('labels a link with the target page title', () {
      expect(
        resolveWikiLinks('See [[log-linear-models]].', _pages),
        'See [Log-Linear Models]'
        '(wiki://pages%2Fconcept%2Flog-linear-models.md).',
      );
    });

    test('uses explicit display text', () {
      expect(
        resolveWikiLinks('[[log-linear-models|these models]]', _pages),
        '[these models](wiki://pages%2Fconcept%2Flog-linear-models.md)',
      );
    });

    test('drops dashes from unresolved slugs', () {
      expect(
        resolveWikiLinks('[[hidden-markov-models]]', _pages),
        '[hidden markov models](wiki://hidden-markov-models)',
      );
    });
  });

  group('numberCitations', () {
    const p1 = 'hypatia://cite?file=crf.pdf&page=1';
    const p2 = 'hypatia://cite?file=crf.pdf&page=2';

    test('numbers citations, merges runs, and reuses repeat numbers', () {
      final out = numberCitations(
        'Claim one [source]($p1) [source]($p2). Claim two [source]($p1).',
      );

      expect(out, startsWith('Claim one[¹]($p1),[²]($p2). Claim two[¹]($p1).'));
      expect(out, contains('#### References'));
      expect(out, contains('1. [crf.pdf, p. 1]($p1)'));
      expect(out, contains('2. [crf.pdf, p. 2]($p2)'));
    });

    test('shows file names for citations that use a file ID', () {
      final out = numberCitations(
        'x [source](hypatia://cite?file=abc&t=342)',
        fileNames: {'abc': 'lecture.mp4'},
      );
      expect(out, contains('1. [lecture.mp4, 5:42]'));
    });

    test('leaves content without citations unchanged', () {
      expect(numberCitations('No sources here.'), 'No sources here.');
    });
  });

  test('citationLocation maps query parameters to viewer locations', () {
    expect(citationLocation(Uri.parse('hypatia://cite?file=a&page=5')), 'p:5');
    expect(citationLocation(Uri.parse('hypatia://cite?file=a&t=12')), 't:12');
    expect(
      citationLocation(Uri.parse('hypatia://cite?file=a&section=intro')),
      's:intro',
    );
    expect(citationLocation(Uri.parse('hypatia://cite?file=a')), '');
  });
}
