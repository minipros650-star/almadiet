/// Daily healthy tips for pregnant women — curated, trimester-aware
class HealthyTips {
  static const List<Map<String, String>> tips = [
    {'tip': 'Drink at least 8-10 glasses of water daily to stay hydrated and support amniotic fluid.', 'emoji': '💧', 'trimester': 'all'},
    {'tip': 'Include iron-rich foods like ragi, drumstick leaves, and dates to prevent anemia.', 'emoji': '🥬', 'trimester': 'all'},
    {'tip': 'Take folic acid supplements as prescribed — they help prevent neural tube defects.', 'emoji': '💊', 'trimester': '1'},
    {'tip': 'Eat small, frequent meals to manage morning sickness in the first trimester.', 'emoji': '🍽️', 'trimester': '1'},
    {'tip': 'Walk for 20-30 minutes daily — gentle exercise improves blood circulation.', 'emoji': '🚶‍♀️', 'trimester': 'all'},
    {'tip': 'Include calcium-rich foods like milk, curd, and paneer for baby\'s bone development.', 'emoji': '🥛', 'trimester': '2'},
    {'tip': 'Avoid raw papaya and pineapple — they may cause uterine contractions.', 'emoji': '⚠️', 'trimester': 'all'},
    {'tip': 'Get enough sleep — 7 to 9 hours is ideal during pregnancy.', 'emoji': '😴', 'trimester': 'all'},
    {'tip': 'Eat protein-rich foods like eggs, lentils, and fish for baby\'s growth.', 'emoji': '🥚', 'trimester': '2'},
    {'tip': 'Practice deep breathing exercises to reduce stress and improve oxygen supply.', 'emoji': '🧘', 'trimester': 'all'},
    {'tip': 'Include whole grains like brown rice and oats for sustained energy.', 'emoji': '🌾', 'trimester': 'all'},
    {'tip': 'Avoid caffeine — limit to one small cup of coffee per day.', 'emoji': '☕', 'trimester': 'all'},
    {'tip': 'Coconut water is excellent for hydration and electrolyte balance.', 'emoji': '🥥', 'trimester': 'all'},
    {'tip': 'Eat vitamin C rich foods like amla, guava, and oranges to boost iron absorption.', 'emoji': '🍊', 'trimester': 'all'},
    {'tip': 'Include omega-3 rich foods like flaxseeds and walnuts for baby\'s brain development.', 'emoji': '🧠', 'trimester': '3'},
    {'tip': 'Avoid lying flat on your back in the third trimester — sleep on your left side.', 'emoji': '🛏️', 'trimester': '3'},
    {'tip': 'Gentle prenatal yoga can help reduce back pain and improve flexibility.', 'emoji': '🧘‍♀️', 'trimester': '2'},
    {'tip': 'Eat fiber-rich foods to prevent constipation, a common pregnancy issue.', 'emoji': '🥗', 'trimester': 'all'},
    {'tip': 'Pack your hospital bag by week 36 — be prepared for your delivery.', 'emoji': '👜', 'trimester': '3'},
    {'tip': 'Keep track of your baby\'s kicks — at least 10 movements in 2 hours is healthy.', 'emoji': '👶', 'trimester': '3'},
  ];

  /// Get a random tip, optionally filtered by trimester
  static Map<String, String> randomTip({int? trimester}) {
    final filtered = trimester != null
        ? tips.where((t) => t['trimester'] == 'all' || t['trimester'] == '$trimester').toList()
        : tips;
    filtered.shuffle();
    return filtered.first;
  }

  /// Get daily tip based on day of year
  static Map<String, String> dailyTip({int? trimester}) {
    final filtered = trimester != null
        ? tips.where((t) => t['trimester'] == 'all' || t['trimester'] == '$trimester').toList()
        : tips;
    final dayOfYear = DateTime.now().difference(DateTime(DateTime.now().year, 1, 1)).inDays;
    return filtered[dayOfYear % filtered.length];
  }
}
