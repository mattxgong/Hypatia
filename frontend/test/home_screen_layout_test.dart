import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/screens/home_screen.dart';

void main() {
  test('side panels preserve the center pane at minimum window width', () {
    final widths = constrainPanelWidths(
      availableWidth: 900,
      sidebarWidth: 250,
      chatWidth: 350,
      sidebarCollapsed: false,
      chatCollapsed: false,
    );

    expect(widths.sidebar + widths.chat, lessThanOrEqualTo(492));
    expect(widths.sidebar, greaterThanOrEqualTo(180));
    expect(widths.chat, greaterThanOrEqualTo(280));
  });

  test('wide layouts retain requested side panel widths', () {
    final widths = constrainPanelWidths(
      availableWidth: 1280,
      sidebarWidth: 250,
      chatWidth: 350,
      sidebarCollapsed: false,
      chatCollapsed: false,
    );

    expect(widths.sidebar, 250);
    expect(widths.chat, 350);
  });

  test('collapsed panels do not consume expanded panel budget', () {
    final widths = constrainPanelWidths(
      availableWidth: 900,
      sidebarWidth: 250,
      chatWidth: 500,
      sidebarCollapsed: true,
      chatCollapsed: false,
    );

    expect(widths.sidebar, 0);
    expect(widths.chat, 464);
  });
}
