import 'package:flutter/material.dart';

class SidebarSearchBar extends StatelessWidget {
  const SidebarSearchBar({super.key});

  @override
  Widget build(BuildContext context) {
    return const TextField(
      decoration: InputDecoration(
        hintText: 'Search wiki...',
        prefixIcon: Icon(Icons.search, size: 18),
        isDense: true,
      ),
    );
  }
}
