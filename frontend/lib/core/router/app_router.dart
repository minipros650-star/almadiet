import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../features/auth/presentation/login_screen.dart';
import '../../features/auth/presentation/register_screen.dart';
import '../../features/home/presentation/home_screen.dart';
import '../../features/health_input/presentation/health_input_screen.dart';
import '../../features/diet_plan/presentation/diet_plan_screen.dart';
import '../../features/diet_plan/presentation/meal_detail_screen.dart';
import '../../features/emergency/presentation/emergency_screen.dart';
import '../../features/profile/presentation/profile_screen.dart';
import '../../features/onboarding/presentation/onboarding_screen.dart';
import '../theme/app_colors.dart';
import '../localization/app_localizations.dart';
import '../../providers/auth_provider.dart';

/// Custom smooth page transition
CustomTransitionPage<void> _fadeSlideTransition(Widget child, GoRouterState state) {
  return CustomTransitionPage(
    key: state.pageKey,
    child: child,
    transitionDuration: const Duration(milliseconds: 350),
    transitionsBuilder: (context, animation, secondaryAnimation, child) {
      final curved = CurvedAnimation(parent: animation, curve: Curves.easeOutCubic);
      return FadeTransition(
        opacity: curved,
        child: SlideTransition(
          position: Tween<Offset>(begin: const Offset(0, 0.04), end: Offset.zero).animate(curved),
          child: child,
        ),
      );
    },
  );
}

final appRouterProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authStateProvider);

  return GoRouter(
    initialLocation: '/splash',
    refreshListenable: _AuthChangeNotifier(ref),
    redirect: (context, state) {
      final isAuthenticated = authState.isAuthenticated;
      final location = state.uri.toString();

      // Splash screen handles initial routing
      if (location == '/splash') return null;

      // Public routes that don't need auth
      final publicRoutes = ['/onboarding', '/login', '/register'];
      final isPublicRoute = publicRoutes.contains(location);

      // If authenticated and on a public route, go to home
      if (isAuthenticated && isPublicRoute) return '/home';

      // If not authenticated and on a protected route, go to login
      if (!isAuthenticated && !isPublicRoute) return '/login';

      return null;
    },
    errorBuilder: (context, state) => Scaffold(
      appBar: AppBar(title: Text(AppLocalizations.of(context).tr('page_not_found'))),
      body: Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text('🔍', style: TextStyle(fontSize: 48)),
          const SizedBox(height: 16),
          Text('Route not found:\n${state.uri}', textAlign: TextAlign.center, style: const TextStyle(fontSize: 16)),
          const SizedBox(height: 24),
          ElevatedButton(onPressed: () => context.go('/home'), child: Text(AppLocalizations.of(context).tr('go_home'))),
        ]),
      ),
    ),
    routes: [
      GoRoute(
        path: '/splash',
        pageBuilder: (context, state) => _fadeSlideTransition(const _SplashScreen(), state),
      ),
      GoRoute(
        path: '/onboarding',
        pageBuilder: (context, state) => _fadeSlideTransition(const OnboardingScreen(), state),
      ),
      GoRoute(
        path: '/login',
        pageBuilder: (context, state) => _fadeSlideTransition(const LoginScreen(), state),
      ),
      GoRoute(
        path: '/register',
        pageBuilder: (context, state) => _fadeSlideTransition(const RegisterScreen(), state),
      ),
      ShellRoute(
        builder: (context, state, child) => _BackButtonGuard(child: HomeShell(child: child)),
        routes: [
          GoRoute(
            path: '/home',
            pageBuilder: (context, state) => _fadeSlideTransition(const HomeScreen(), state),
          ),
          GoRoute(
            path: '/diet',
            pageBuilder: (context, state) => _fadeSlideTransition(const DietPlanScreen(), state),
          ),
          GoRoute(
            path: '/emergency',
            pageBuilder: (context, state) => _fadeSlideTransition(const EmergencyScreen(), state),
          ),
          GoRoute(
            path: '/profile',
            pageBuilder: (context, state) => _fadeSlideTransition(const ProfileScreen(), state),
          ),
        ],
      ),
      GoRoute(
        path: '/health-input',
        pageBuilder: (context, state) => _fadeSlideTransition(const HealthInputScreen(), state),
      ),
      GoRoute(
        path: '/meal/:mealId',
        pageBuilder: (context, state) {
          final mealId = state.pathParameters['mealId'] ?? '';
          if (mealId.isEmpty) {
            return _fadeSlideTransition(
              Scaffold(appBar: AppBar(), body: const Center(child: Text('Invalid meal ID'))),
              state,
            );
          }
          return _fadeSlideTransition(MealDetailScreen(mealId: mealId), state);
        },
      ),
    ],
  );
});

/// Prevents accidental app exit — shows confirmation dialog
class _BackButtonGuard extends StatelessWidget {
  final Widget child;
  const _BackButtonGuard({required this.child});

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) return;
        final l = AppLocalizations.of(context);
        final shouldExit = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            title: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AppColors.primary.withValues(alpha: 0.1),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.favorite, color: AppColors.primary, size: 22),
                ),
                const SizedBox(width: 12),
                Text(l.tr('exit_title')),
              ],
            ),
            content: Text(l.tr('exit_msg')),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: Text(l.tr('stay'), style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w600)),
              ),
              TextButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: Text(l.tr('exit'), style: TextStyle(color: AppColors.textSecondary)),
              ),
            ],
          ),
        );
        if (shouldExit == true) {
          SystemNavigator.pop();
        }
      },
      child: child,
    );
  }
}

/// Bottom navigation shell with animated icons
class HomeShell extends StatelessWidget {
  final Widget child;
  const HomeShell({super.key, required this.child});

  static int _indexFromLocation(String location) {
    if (location.startsWith('/diet')) return 1;
    if (location.startsWith('/emergency')) return 2;
    if (location.startsWith('/profile')) return 3;
    return 0;
  }

  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).uri.toString();
    final currentIndex = _indexFromLocation(location);
    final l = AppLocalizations.of(context);

    return Scaffold(
      body: AnimatedSwitcher(
        duration: const Duration(milliseconds: 300),
        switchInCurve: Curves.easeOutCubic,
        child: child,
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.08), blurRadius: 20, offset: const Offset(0, -4))],
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _NavItem(icon: Icons.home_rounded, label: l.tr('home'), isSelected: currentIndex == 0, onTap: () => context.go('/home')),
                _NavItem(icon: Icons.restaurant_menu_rounded, label: l.tr('diet'), isSelected: currentIndex == 1, onTap: () => context.go('/diet')),
                _NavItem(icon: Icons.emergency_rounded, label: l.tr('emergency'), isSelected: currentIndex == 2, onTap: () => context.go('/emergency')),
                _NavItem(icon: Icons.person_rounded, label: l.tr('profile'), isSelected: currentIndex == 3, onTap: () => context.go('/profile')),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isSelected;
  final VoidCallback onTap;
  const _NavItem({required this.icon, required this.label, required this.isSelected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOutCubic,
        padding: EdgeInsets.symmetric(horizontal: isSelected ? 12 : 8, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? AppColors.primary.withValues(alpha: 0.1) : Colors.transparent,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: isSelected ? AppColors.primary : AppColors.textSecondary, size: 22),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                color: isSelected ? AppColors.primary : AppColors.textSecondary,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                fontSize: 10,
              ),
              overflow: TextOverflow.ellipsis,
              maxLines: 1,
            ),
          ],
        ),
      ),
    );
  }
}

/// Notifies GoRouter when auth state changes so redirect logic re-runs
class _AuthChangeNotifier extends ChangeNotifier {
  _AuthChangeNotifier(Ref ref) {
    ref.listen<AuthState>(authStateProvider, (_, _) => notifyListeners());
  }
}

/// Splash screen that checks auth token and routes accordingly
class _SplashScreen extends ConsumerStatefulWidget {
  const _SplashScreen();
  @override
  ConsumerState<_SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends ConsumerState<_SplashScreen> {
  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    // Give auth provider time to check saved token
    await Future.delayed(const Duration(milliseconds: 800));

    if (!mounted) return;

    final auth = ref.read(authStateProvider);
    if (auth.isAuthenticated) {
      context.go('/home');
    } else {
      // Check if onboarding was already seen
      final prefs = await SharedPreferences.getInstance();
      final seenOnboarding = prefs.getBool('onboarding_seen') ?? false;
      if (mounted) {
        context.go(seenOnboarding ? '/login' : '/onboarding');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Container(
            width: 90, height: 90,
            decoration: BoxDecoration(
              gradient: AppColors.primaryGradient,
              shape: BoxShape.circle,
              boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.25), blurRadius: 20)],
            ),
            child: const Center(child: Text('🌸', style: TextStyle(fontSize: 40))),
          ),
          const SizedBox(height: 24),
          const Text('AlmaDiet', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800)),
          const SizedBox(height: 24),
          SizedBox(width: 32, height: 32, child: CircularProgressIndicator(color: AppColors.primary, strokeWidth: 3)),
        ]),
      ),
    );
  }
}
