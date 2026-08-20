import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'config/theme.dart';
import 'providers/class_provider.dart';
import 'providers/theme_provider.dart';
import 'screens/home_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final classes = ref.read(classListProvider);
  final defaultClassId = classes.isNotEmpty ? classes.first.id : null;

  return GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(
        path: '/',
        redirect: (context, state) {
          if (defaultClassId != null) return '/class/$defaultClassId';
          return null;
        },
        builder: (context, state) => const _NoClassesScreen(),
      ),
      GoRoute(
        path: '/class/:classId',
        builder: (context, state) {
          final classId = state.pathParameters['classId']!;
          return _ClassRouteSync(classId: classId, child: const HomeScreen());
        },
      ),
    ],
  );
});

class _ClassRouteSync extends ConsumerStatefulWidget {
  const _ClassRouteSync({required this.classId, required this.child});

  final String classId;
  final Widget child;

  @override
  ConsumerState<_ClassRouteSync> createState() => _ClassRouteSyncState();
}

class _ClassRouteSyncState extends ConsumerState<_ClassRouteSync> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      ref.read(currentClassIdProvider.notifier).state = widget.classId;
    });
  }

  @override
  void didUpdateWidget(covariant _ClassRouteSync oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.classId != widget.classId) {
      ref.read(currentClassIdProvider.notifier).state = widget.classId;
    }
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

class _NoClassesScreen extends StatelessWidget {
  const _NoClassesScreen();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.school_outlined,
              size: 64,
              color: Theme.of(context).colorScheme.primary,
            ),
            const SizedBox(height: 16),
            Text(
              'Welcome to Hypatia',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 8),
            const Text('Create a class to get started.'),
          ],
        ),
      ),
    );
  }
}

class HypatiaShell extends ConsumerWidget {
  const HypatiaShell({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeMode = ref.watch(themeModeProvider);
    final router = ref.watch(routerProvider);

    return MaterialApp.router(
      title: 'Hypatia',
      debugShowCheckedModeBanner: false,
      theme: HypatiaTheme.lightTheme,
      darkTheme: HypatiaTheme.darkTheme,
      themeMode: themeMode,
      routerConfig: router,
    );
  }
}
