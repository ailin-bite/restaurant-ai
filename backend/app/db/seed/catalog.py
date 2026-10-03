"""Справочные данные ресторана «Терра»: столики, меню, рецепты, продукты,
смена и постоянные гости. Отделены от логики наполнения, чтобы параметры
ресторана можно было менять без правки кода генератора."""

from app.core.enums import (
    InventoryUnit,
    LoyaltyTier,
    MenuCategory,
    PreferenceKind,
    ReviewTopic,
    Sentiment,
    StaffRole,
    Station,
    Zone,
)

def _tables():
    """Зал на 200 мест: основной зал 110, терраса 50, VIP 28, бар 12."""

    rows = []

    def add(prefix, zone, seats_list, cols, y0):
        for i, seats in enumerate(seats_list):
            number = str(i + 1) if prefix == "" else f"{prefix}{i + 1}"
            rows.append((number, zone, seats, i % cols, y0 + i // cols))

    add("", Zone.MAIN, [2] * 10 + [4] * 15 + [6] * 5, 6, 0)  # 30 столов, 110 мест
    add("T", Zone.TERRACE, [2] * 3 + [4] * 8 + [6] * 2, 5, 6)  # 13 столов, 50 мест
    add("V", Zone.VIP, [8, 8, 6, 6], 2, 0)  # 4 стола, 28 мест
    add("B", Zone.BAR, [2] * 6, 3, 3)  # 6 столов, 12 мест
    return rows


TABLES = _tables()
SEATS_TOTAL = sum(seats for _n, _z, seats, _x, _y in TABLES)
assert SEATS_TOTAL == 200, SEATS_TOTAL

# Остатки рассчитаны на смену зала на 200 мест. Курица оставлена короткой:
# вечерний спрос её обгонит, и предупреждение о нехватке появится из данных.
INVENTORY = [
    ("Куриная грудка", InventoryUnit.KG, 1.44, 0.18, 16.0, 6.0, "Фермер Плюс", 24),
    ("Рибай говяжий", InventoryUnit.KG, 12.0, 0.30, 22.0, 8.0, "Мясной двор", 48),
    ("Фарш говяжий", InventoryUnit.KG, 8.0, 0.20, 16.0, 6.0, "Мясной двор", 48),
    ("Лосось", InventoryUnit.KG, 6.0, 0.22, 14.0, 5.0, "Северная рыба", 36),
    ("Тунец консервированный", InventoryUnit.KG, 3.2, 0.08, 8.0, 2.5, "Опт-Фуд", 24),
    ("Креветки", InventoryUnit.KG, 3.0, 0.10, 8.0, 2.5, "Северная рыба", 36),
    ("Паста спагетти", InventoryUnit.KG, 16.0, 0.12, 26.0, 8.0, "Опт-Фуд", 24),
    ("Рис арборио", InventoryUnit.KG, 6.5, 0.09, 13.0, 4.0, "Опт-Фуд", 24),
    ("Шампиньоны", InventoryUnit.KG, 5.2, 0.10, 11.0, 4.0, "Зелёный рынок", 12),
    ("Картофель", InventoryUnit.KG, 38.0, 0.20, 52.0, 16.0, "Зелёный рынок", 12),
    ("Томаты", InventoryUnit.KG, 13.0, 0.12, 21.0, 7.0, "Зелёный рынок", 12),
    ("Огурцы", InventoryUnit.KG, 8.0, 0.08, 13.0, 4.0, "Зелёный рынок", 12),
    ("Салат романо", InventoryUnit.KG, 3.8, 0.07, 8.0, 2.5, "Зелёный рынок", 12),
    ("Пармезан", InventoryUnit.KG, 2.8, 0.03, 5.0, 1.6, "Опт-Фуд", 24),
    ("Сыр фета", InventoryUnit.KG, 2.6, 0.05, 5.0, 1.6, "Опт-Фуд", 24),
    ("Сливки 33%", InventoryUnit.LITER, 8.0, 0.08, 13.0, 4.0, "Молоко-Сервис", 24),
    ("Яйца", InventoryUnit.PCS, 240.0, 1.0, 320.0, 100.0, "Фермер Плюс", 24),
    ("Булочка для бургера", InventoryUnit.PCS, 64.0, 1.0, 110.0, 32.0, "Пекарня №1", 12),
    ("Маскарпоне", InventoryUnit.KG, 3.2, 0.07, 5.0, 1.6, "Опт-Фуд", 24),
    ("Кофе в зёрнах", InventoryUnit.KG, 6.4, 0.012, 11.0, 2.5, "Кофе Трейд", 48),
    ("Вино красное", InventoryUnit.LITER, 20.0, 0.15, 32.0, 10.0, "Винный дом", 72),
    ("Лимоны", InventoryUnit.KG, 5.2, 0.05, 11.0, 3.0, "Зелёный рынок", 12),
    ("Кокосовое молоко", InventoryUnit.LITER, 8.0, 0.12, 13.0, 4.0, "Опт-Фуд", 24),
    ("Овощи для гриля", InventoryUnit.KG, 9.5, 0.22, 16.0, 5.0, "Зелёный рынок", 12),
    ("Тыква", InventoryUnit.KG, 7.4, 0.15, 13.0, 4.0, "Зелёный рынок", 12),
    ("Свёкла", InventoryUnit.KG, 8.4, 0.12, 13.0, 4.0, "Зелёный рынок", 12),
]

# (название, категория, станция, цена, минут готовки, сложность, вегетарианское, острое)
MENU = [
    ("Цезарь с курицей", MenuCategory.COLD, Station.COLD_LINE, 620, 8, 2, False, False),
    ("Греческий салат", MenuCategory.COLD, Station.COLD_LINE, 540, 7, 1, True, False),
    ("Салат с тунцом", MenuCategory.COLD, Station.COLD_LINE, 690, 9, 2, False, False),
    ("Крем-суп из тыквы", MenuCategory.HOT, Station.HOT_LINE, 420, 10, 1, True, False),
    ("Борщ", MenuCategory.HOT, Station.HOT_LINE, 450, 12, 2, False, False),
    ("Том-ям", MenuCategory.HOT, Station.HOT_LINE, 780, 14, 3, False, True),
    ("Паста карбонара", MenuCategory.HOT, Station.HOT_LINE, 720, 14, 2, False, False),
    (
        "Паста с томатами и базиликом",
        MenuCategory.HOT,
        Station.HOT_LINE,
        640,
        12,
        2,
        True,
        False,
    ),
    ("Ризотто с грибами", MenuCategory.HOT, Station.HOT_LINE, 760, 18, 3, True, False),
    ("Стейк рибай", MenuCategory.HOT, Station.GRILL, 2450, 22, 4, False, False),
    (
        "Куриная грудка на гриле",
        MenuCategory.HOT,
        Station.GRILL,
        780,
        16,
        2,
        False,
        False,
    ),
    ("Бургер с говядиной", MenuCategory.HOT, Station.GRILL, 890, 15, 3, False, False),
    ("Лосось на гриле", MenuCategory.HOT, Station.GRILL, 1350, 18, 4, False, False),
    ("Овощи на гриле", MenuCategory.HOT, Station.GRILL, 560, 12, 1, True, False),
    ("Картофель фри", MenuCategory.HOT, Station.GRILL, 320, 8, 1, True, False),
    ("Тирамису", MenuCategory.DESSERT, Station.PASTRY, 480, 6, 2, True, False),
    ("Чизкейк", MenuCategory.DESSERT, Station.PASTRY, 460, 5, 1, True, False),
    ("Лимонад домашний", MenuCategory.BAR, Station.BAR, 290, 4, 1, True, False),
    ("Эспрессо", MenuCategory.BAR, Station.BAR, 180, 3, 1, True, False),
    ("Бокал вина", MenuCategory.BAR, Station.BAR, 520, 2, 1, True, False),
]

# блюдо -> [(продукт, расход на порцию)]
RECIPES = {
    "Цезарь с курицей": [
        ("Салат романо", 0.07),
        ("Куриная грудка", 0.12),
        ("Пармезан", 0.02),
        ("Яйца", 0.5),
    ],
    "Греческий салат": [("Томаты", 0.12), ("Огурцы", 0.08), ("Сыр фета", 0.05)],
    "Салат с тунцом": [
        ("Тунец консервированный", 0.08),
        ("Салат романо", 0.05),
        ("Томаты", 0.06),
    ],
    "Крем-суп из тыквы": [("Тыква", 0.15), ("Сливки 33%", 0.05)],
    "Борщ": [("Свёкла", 0.12), ("Фарш говяжий", 0.08), ("Картофель", 0.08)],
    "Том-ям": [("Креветки", 0.10), ("Кокосовое молоко", 0.12), ("Лимоны", 0.03)],
    "Паста карбонара": [
        ("Паста спагетти", 0.12),
        ("Сливки 33%", 0.08),
        ("Пармезан", 0.03),
        ("Яйца", 1.0),
    ],
    "Паста с томатами и базиликом": [
        ("Паста спагетти", 0.12),
        ("Томаты", 0.15),
        ("Пармезан", 0.02),
    ],
    "Ризотто с грибами": [
        ("Рис арборио", 0.09),
        ("Шампиньоны", 0.10),
        ("Пармезан", 0.03),
        ("Сливки 33%", 0.04),
    ],
    "Стейк рибай": [("Рибай говяжий", 0.30), ("Овощи для гриля", 0.08)],
    "Куриная грудка на гриле": [
        ("Куриная грудка", 0.18),
        ("Овощи для гриля", 0.10),
    ],
    "Бургер с говядиной": [
        ("Фарш говяжий", 0.20),
        ("Булочка для бургера", 1.0),
        ("Томаты", 0.04),
        ("Картофель", 0.12),
    ],
    "Лосось на гриле": [
        ("Лосось", 0.22),
        ("Лимоны", 0.03),
        ("Овощи для гриля", 0.08),
    ],
    "Овощи на гриле": [("Овощи для гриля", 0.22)],
    "Картофель фри": [("Картофель", 0.20)],
    "Тирамису": [("Маскарпоне", 0.07), ("Кофе в зёрнах", 0.008), ("Яйца", 0.5)],
    "Чизкейк": [("Маскарпоне", 0.06), ("Сливки 33%", 0.03)],
    "Лимонад домашний": [("Лимоны", 0.05)],
    "Эспрессо": [("Кофе в зёрнах", 0.012)],
    "Бокал вина": [("Вино красное", 0.15)],
}

# Смена на 200 мест: ~1 официант на 18 мест, кухня с узким местом на гриле.
STAFF = (
    [("Официант %d" % i, StaffRole.WAITER, Zone.MAIN, None, 5, 450) for i in range(1, 7)]
    + [("Официант %d" % i, StaffRole.WAITER, Zone.TERRACE, None, 5, 450) for i in range(7, 10)]
    + [("Официант %d" % i, StaffRole.WAITER, Zone.VIP, None, 3, 480) for i in range(10, 12)]
    + [
        ("Повар 1", StaffRole.COOK, None, Station.GRILL, 6, 600),
        ("Повар 2", StaffRole.COOK, None, Station.GRILL, 6, 600),
        ("Повар 3", StaffRole.COOK, None, Station.GRILL, 6, 600),
        ("Повар 4", StaffRole.COOK, None, Station.HOT_LINE, 5, 560),
        ("Повар 5", StaffRole.COOK, None, Station.HOT_LINE, 5, 560),
        ("Повар 6", StaffRole.COOK, None, Station.HOT_LINE, 5, 560),
        ("Повар 7", StaffRole.COOK, None, Station.COLD_LINE, 5, 520),
        ("Повар 8", StaffRole.COOK, None, Station.COLD_LINE, 5, 520),
        ("Повар 9", StaffRole.COOK, None, Station.PASTRY, 4, 520),
        ("Хостес 1", StaffRole.HOST, Zone.MAIN, None, 8, 420),
        ("Хостес 2", StaffRole.HOST, Zone.TERRACE, None, 8, 420),
        ("Раннер 1", StaffRole.RUNNER, Zone.PASS, None, 8, 400),
        ("Раннер 2", StaffRole.RUNNER, Zone.PASS, None, 8, 400),
        ("Бармен 1", StaffRole.BARTENDER, Zone.BAR, Station.BAR, 6, 500),
        ("Бармен 2", StaffRole.BARTENDER, Zone.BAR, Station.BAR, 6, 500),
    ]
)

# (имя, телефон, визитов, средний чек, уровень, [(тип предпочтения, значение)], заметка)
GUESTS = [
    (
        "Мария Левина",
        "+7 915 220-14-08",
        4,
        1840,
        LoyaltyTier.REGULAR,
        [
            (PreferenceKind.DIET, "вегетарианские блюда"),
            (PreferenceKind.DISLIKE, "острое"),
            (PreferenceKind.FAVORITE_DISH, "Паста с томатами и базиликом"),
            (PreferenceKind.SEATING, "терраса"),
        ],
        "Предпочитает столик у окна, обычно приходит вдвоём.",
    ),
    (
        "Антон Руднев",
        "+7 903 551-77-21",
        9,
        4200,
        LoyaltyTier.VIP,
        [
            (PreferenceKind.FAVORITE_DISH, "Стейк рибай"),
            (PreferenceKind.DISLIKE, "шум"),
            (PreferenceKind.SEATING, "VIP-зал"),
        ],
        "Часто приводит деловых партнёров, просит тихий зал.",
    ),
    (
        "Елена Сорокина",
        "+7 926 410-32-56",
        6,
        2300,
        LoyaltyTier.REGULAR,
        [
            (PreferenceKind.ALLERGY, "орехи"),
            (PreferenceKind.FAVORITE_DISH, "Лосось на гриле"),
        ],
        "Аллергия на орехи — обязательно уточнять состав десертов.",
    ),
    (
        "Дмитрий Фомин",
        "+7 916 884-19-03",
        3,
        1500,
        LoyaltyTier.REGULAR,
        [(PreferenceKind.FAVORITE_DISH, "Бургер с говядиной")],
        None,
    ),
    (
        "Ольга Жук",
        "+7 905 332-66-70",
        7,
        2650,
        LoyaltyTier.REGULAR,
        [
            (PreferenceKind.DIET, "рыба, без мяса"),
            (PreferenceKind.FAVORITE_DISH, "Салат с тунцом"),
        ],
        None,
    ),
    (
        "Игорь Савельев",
        "+7 909 771-25-14",
        2,
        1200,
        LoyaltyTier.NEW,
        [(PreferenceKind.FAVORITE_DISH, "Паста карбонара")],
        None,
    ),
    (
        "Наталья Белкина",
        "+7 917 203-88-45",
        5,
        1980,
        LoyaltyTier.REGULAR,
        [
            (PreferenceKind.DISLIKE, "острое"),
            (PreferenceKind.FAVORITE_DISH, "Ризотто с грибами"),
        ],
        None,
    ),
    (
        "Кирилл Дорн",
        "+7 985 119-40-62",
        11,
        3900,
        LoyaltyTier.VIP,
        [
            (PreferenceKind.FAVORITE_DISH, "Том-ям"),
            (PreferenceKind.DIET, "любит острое"),
        ],
        "Постоянный гость пятниц, всегда просит добавить острого.",
    ),
    ("Алина Ветрова", "+7 962 554-07-19", 1, 890, LoyaltyTier.NEW, [], None),
    (
        "Сергей Пахомов",
        "+7 921 636-82-33",
        4,
        2100,
        LoyaltyTier.REGULAR,
        [
            (PreferenceKind.ALLERGY, "лактоза"),
            (PreferenceKind.FAVORITE_DISH, "Овощи на гриле"),
        ],
        None,
    ),
    (
        "Вера Ильина",
        "+7 999 471-50-28",
        8,
        2450,
        LoyaltyTier.REGULAR,
        [(PreferenceKind.FAVORITE_DISH, "Тирамису")],
        None,
    ),
    ("Максим Королёв", "+7 936 228-93-17", 2, 1350, LoyaltyTier.NEW, [], None),
    (
        "Юлия Громова",
        "+7 911 345-61-04",
        6,
        2890,
        LoyaltyTier.REGULAR,
        [
            (PreferenceKind.DIET, "вегетарианские блюда"),
            (PreferenceKind.FAVORITE_DISH, "Греческий салат"),
        ],
        None,
    ),
    (
        "Роман Тихонов",
        "+7 964 802-37-91",
        3,
        1700,
        LoyaltyTier.REGULAR,
        [(PreferenceKind.FAVORITE_DISH, "Куриная грудка на гриле")],
        None,
    ),
]

# Тексты отзывов по тональности и теме. Темы берутся из фиксированного
# справочника ReviewTopic — иначе нельзя считать доли по неделям.
REVIEW_TEMPLATES = {
    Sentiment.NEGATIVE: {
        ReviewTopic.WAIT_TIME: [
            "Горячее ждали почти 40 минут, хотя зал был заполнен наполовину.",
            "Очень долго несли блюда, пришлось напоминать дважды.",
            "Пришли на бизнес-ланч, ждали заказ 35 минут — опоздали на встречу.",
            "Кухня явно не справлялась: салаты принесли вместе с десертом.",
            "Ожидание между подачами слишком большое, вечером это утомляет.",
        ],
        ReviewTopic.SERVICE: [
            "Официант подошёл не сразу, пришлось искать его по залу.",
            "Счёт несли очень долго, хотя мы предупредили, что торопимся.",
        ],
        ReviewTopic.FOOD_QUALITY: [
            "Стейк пережарили, просили медиум.",
            "Паста оказалась пересоленной, есть было сложно.",
        ],
        ReviewTopic.ORDER_ERROR: [
            "Принесли не то блюдо, переделывали заказ.",
            "Забыли про гарнир, вспомнили только после вопроса.",
        ],
        ReviewTopic.PRICE: [
            "Для таких порций цена кажется завышенной.",
        ],
        ReviewTopic.CLEANLINESS: [
            "Столик протёрли только после просьбы.",
        ],
        ReviewTopic.NOISE: [
            "Очень шумно, музыка громче разговора.",
        ],
    },
    Sentiment.NEUTRAL: {
        ReviewTopic.FOOD_QUALITY: [
            "Еда нормальная, ничего особенного, но и претензий нет.",
            "Обычный ужин: вкусно, но без восторга.",
        ],
        ReviewTopic.WAIT_TIME: [
            "Ждали около 20 минут — терпимо для вечера пятницы.",
        ],
        ReviewTopic.SERVICE: [
            "Обслуживание ровное, без запоминающихся деталей.",
        ],
    },
    Sentiment.POSITIVE: {
        ReviewTopic.FOOD_QUALITY: [
            "Лосось на гриле великолепный, вернёмся ещё.",
            "Ризотто одно из лучших в городе.",
            "Десерты отличные, тирамису очень нежный.",
        ],
        ReviewTopic.SERVICE: [
            "Официант помнил наши предпочтения — очень приятно.",
            "Внимательный персонал, подсказали удачное вино.",
        ],
        ReviewTopic.CLEANLINESS: [
            "Чисто, уютно, приятная атмосфера.",
        ],
        ReviewTopic.WAIT_TIME: [
            "Всё принесли быстро, ждать не пришлось.",
        ],
    },
}
