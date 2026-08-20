import 'package:flutter/material.dart';

class AddFileButton extends StatelessWidget {
  const AddFileButton({super.key});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        onPressed: () {},
        icon: const Icon(Icons.add, size: 18),
        label: const Text('Add Files'),
      ),
    );
  }
}
