from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
import random
from datetime import timedelta

from catalog.models import (
    Product, ProductCategory, Size, ProductColor, ProductWidth,
    ProductAttribute, Specification, SpecificationValue, ProductSpecification,
    ProductReview, ProductSale, PromoCode
)


class Command(BaseCommand):
    help = 'Генерує тестові дані для каталогу товарів'

    def add_arguments(self, parser):
        parser.add_argument(
            '--categories',
            type=int,
            default=8,
            help='Кількість категорій для створення (за замовчуванням: 8)'
        )
        parser.add_argument(
            '--products',
            type=int,
            default=50,
            help='Кількість товарів для створення (за замовчуванням: 50)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Очистити існуючі дані перед створенням нових'
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Очищення існуючих даних...')
            self.clear_data()

        self.stdout.write('Початок генерації тестових даних...')
        
        with transaction.atomic():
            # Створюємо категорії
            categories = self.create_categories(options['categories'])
            
            # Створюємо розміри
            sizes = self.create_sizes()
            
            # Створюємо кольори
            colors = self.create_colors()
            
            # Створюємо ширини
            widths = self.create_widths()
            
            # Створюємо специфікації
            specifications = self.create_specifications()
            
            # Створюємо товари
            products = self.create_products(options['products'], categories, colors)
            
            # Створюємо атрибути товарів
            self.create_product_attributes(products, sizes, widths)
            
            # Створюємо специфікації товарів
            self.create_product_specifications(products, specifications)
            
            # Створюємо відгуки
            self.create_reviews(products)
            
            # Створюємо акції
            self.create_sales(products)
            
            # Створюємо промокоди
            self.create_promocodes()

        self.stdout.write(
            self.style.SUCCESS(
                f'Успішно створено:\n'
                f'- {len(categories)} категорій\n'
                f'- {len(products)} товарів\n'
                f'- {len(sizes)} розмірів\n'
                f'- {len(colors)} кольорів\n'
                f'- {len(specifications)} специфікацій\n'
                f'- Відгуки, акції та промокоди'
            )
        )

    def clear_data(self):
        """Очищає існуючі дані"""
        ProductReview.objects.all().delete()
        ProductSpecification.objects.all().delete()
        ProductAttribute.objects.all().delete()
        Product.objects.all().delete()
        ProductCategory.objects.all().delete()
        Size.objects.all().delete()
        ProductColor.objects.all().delete()
        ProductWidth.objects.all().delete()
        Specification.objects.all().delete()
        SpecificationValue.objects.all().delete()
        ProductSale.objects.all().delete()
        PromoCode.objects.all().delete()

    def create_categories(self, count):
        """Створює категорії товарів"""
        categories_data = [
            {'title': 'Килими', 'description': 'Якісні килими для вашого дому'},
            {'title': 'Покриття для підлоги', 'description': 'Сучасні покриття для підлоги'},
            {'title': 'Декор', 'description': 'Декоративні елементи для інтер\'єру'},
            {'title': 'Меблі', 'description': 'Стильні меблі для будь-якого приміщення'},
            {'title': 'Освітлення', 'description': 'Сучасні світильники та лампи'},
            {'title': 'Текстиль', 'description': 'Текстильні вироби для дому'},
            {'title': 'Сантехніка', 'description': 'Якісна сантехніка'},
            {'title': 'Побутова техніка', 'description': 'Надійна побутова техніка'},
            {'title': 'Кухонні прилади', 'description': 'Якісні кухонні прилади'},
            {'title': 'Садові меблі', 'description': 'Комфортні меблі для саду'},
            {'title': 'Дитячі товари', 'description': 'Безпечні товари для дітей'},
            {'title': 'Спортивні товари', 'description': 'Товари для спорту та активного відпочинку'},
        ]
        
        categories = []
        for i in range(min(count, len(categories_data))):
            data = categories_data[i]
            category = ProductCategory.objects.create(
                title=data['title']
            )
            categories.append(category)
            self.stdout.write(f'Створено категорію: {category.title}')
        
        return categories

    def create_sizes(self):
        """Створює розміри товарів"""
        sizes_data = [
            'Маленький', 'Середній', 'Великий', 'Дуже великий', 'Гігантський',
            '50x50', '100x100', '150x150', '200x200', '250x250', '300x300',
            'S', 'M', 'L', 'XL', 'XXL', 'XXXL',
            'Дитячий', 'Підлітковий', 'Дорослий',
            'Стандарт', 'Великий формат', 'Екстра великий'
        ]
        
        sizes = []
        for size_title in sizes_data:
            size, created = Size.objects.get_or_create(title=size_title)
            if created:
                self.stdout.write(f'Створено розмір: {size.title}')
            sizes.append(size)
        
        return sizes

    def create_colors(self):
        """Створює кольори товарів"""
        colors_data = [
            {'title': 'Червоний', 'color': '#FF0000'},
            {'title': 'Синій', 'color': '#0000FF'},
            {'title': 'Зелений', 'color': '#00FF00'},
            {'title': 'Жовтий', 'color': '#FFFF00'},
            {'title': 'Чорний', 'color': '#000000'},
            {'title': 'Білий', 'color': '#FFFFFF'},
            {'title': 'Сірий', 'color': '#808080'},
            {'title': 'Коричневий', 'color': '#A52A2A'},
            {'title': 'Бежевий', 'color': '#F5F5DC'},
            {'title': 'Рожевий', 'color': '#FFC0CB'},
            {'title': 'Помаранчевий', 'color': '#FFA500'},
            {'title': 'Фіолетовий', 'color': '#800080'},
            {'title': 'Блакитний', 'color': '#87CEEB'},
            {'title': 'Темно-синій', 'color': '#00008B'},
            {'title': 'Світло-зелений', 'color': '#90EE90'},
            {'title': 'Темно-зелений', 'color': '#006400'},
            {'title': 'Золотий', 'color': '#FFD700'},
            {'title': 'Срібний', 'color': '#C0C0C0'},
            {'title': 'Бордовий', 'color': '#800020'},
        ]
        
        colors = []
        for color_data in colors_data:
            color, created = ProductColor.objects.get_or_create(
                title=color_data['title'],
                defaults={'color': color_data['color']}
            )
            if created:
                self.stdout.write(f'Створено колір: {color.title}')
            colors.append(color)
        
        return colors

    def create_widths(self):
        """Створює ширини товарів"""
        widths_data = [Decimal('0.5'), Decimal('1.0'), Decimal('1.5'), Decimal('2.0'), Decimal('2.5'), Decimal('3.0')]
        
        widths = []
        for width_value in widths_data:
            width, created = ProductWidth.objects.get_or_create(width=width_value)
            if created:
                self.stdout.write(f'Створено ширину: {width.width}')
            widths.append(width)
        
        return widths

    def create_specifications(self):
        """Створює специфікації товарів"""
        specs_data = [
            {
                'title': 'Колір',
                'values': ['Червоний', 'Синій', 'Зелений', 'Чорний', 'Білий', 'Сірий', 'Коричневий', 'Бежевий', 'Рожевий', 'Помаранчевий', 'Фіолетовий', 'Блакитний']
            },
            {
                'title': 'Матеріал',
                'values': ['Шерсть', 'Бавовна', 'Поліестер', 'Шовк', 'Льон', 'Акрил', 'Дерево', 'Метал', 'Скло', 'Пластик', 'Кераміка', 'Текстиль']
            },
            {
                'title': 'Стиль',
                'values': ['Класичний', 'Сучасний', 'Мінімалізм', 'Вікторіанський', 'Скандинавський', 'Промисловий', 'Ретро', 'Хай-тек', 'Еко', 'Бохо']
            },
            {
                'title': 'Тип',
                'values': ['Килим', 'Покриття', 'Декор', 'Меблі', 'Освітлення', 'Сантехніка', 'Техніка', 'Текстиль', 'Кухонні прилади', 'Садові товари']
            },
            {
                'title': 'Бренд',
                'values': ['IKEA', 'Ashley', 'Pottery Barn', 'West Elm', 'Crate & Barrel', 'Restoration Hardware', 'Ethan Allen', 'La-Z-Boy', 'Herman Miller', 'Knoll']
            },
            {
                'title': 'Країна виробник',
                'values': ['Україна', 'Німеччина', 'Італія', 'Швеція', 'Данія', 'Франція', 'США', 'Китай', 'Польща', 'Чехія']
            }
        ]
        
        specifications = []
        for spec_data in specs_data:
            spec, created = Specification.objects.get_or_create(title=spec_data['title'])
            if created:
                self.stdout.write(f'Створено специфікацію: {spec.title}')
            
            for value_title in spec_data['values']:
                value, created = SpecificationValue.objects.get_or_create(
                    title=value_title
                )
                if created:
                    self.stdout.write(f'  - Створено значення: {value.title}')
            
            specifications.append(spec)
        
        return specifications

    def create_products(self, count, categories, colors):
        """Створює товари"""
        product_names = [
            # Килими та покриття
            'Елегантний килим "Комфорт"',
            'Сучасне покриття "Модерн"',
            'Якісний килим "Традиція"',
            'Сучасне покриття "Інновація"',
            'Класичний килим "Елеганс"',
            'Мінімалістичне покриття "Стиль"',
            'Вікторіанський килим "Розкіш"',
            'Скандинавське покриття "Простір"',
            'Орієнтальний килим "Екзотика"',
            'Промислове покриття "Лофт"',
            
            # Декор
            'Декоративна подушка "Стиль"',
            'Декоративна ваза "Арт"',
            'Декоративна картина "Враження"',
            'Декоративна статуетка "Краса"',
            'Декоративна рамка "Пам\'ять"',
            'Декоративна свічка "Романтика"',
            'Декоративна квітка "Природа"',
            'Декоративна тарілка "Колекція"',
            'Декоративна коробка "Скарб"',
            'Декоративна подушка "Комфорт"',
            
            # Меблі
            'Комфортне крісло "Релакс"',
            'Елегантний диван "Комфорт Плюс"',
            'Стильний стіл "Модерн"',
            'Комфортне ліжко "Сон"',
            'Елегантний шкаф "Організація"',
            'Стильний стілець "Ергономіка"',
            'Сучасний комод "Порядок"',
            'Класичний буфет "Традиція"',
            'Мінімалістичний стіл "Функція"',
            'Вікторіанське крісло "Розкіш"',
            
            # Освітлення
            'Стильний світильник "Світло"',
            'Стильна лампа "Освітлення"',
            'Сучасна люстра "Велич"',
            'Мінімалістичний бра "Стиль"',
            'Класична настільна лампа "Робота"',
            'Скандинавський світильник "Простір"',
            'Промислова лампа "Лофт"',
            'Романтична люстра "Вечір"',
            'Функціональний світильник "День"',
            'Декоративна лампа "Настрій"',
            
            # Текстиль
            'Якісна скатертина "Елеганс"',
            'Якісна ковдра "Тепло"',
            'Стильна подушка "Комфорт"',
            'Елегантна скатертина "Вечір"',
            'М\'яка ковдра "Сон"',
            'Декоративна подушка "Стиль"',
            'Класична скатертина "Традиція"',
            'Сучасна ковдра "Модерн"',
            'Вікторіанська подушка "Розкіш"',
            'Скандинавська скатертина "Простір"',
            
            # Сантехніка
            'Сучасний унітаз "Гігієна"',
            'Елегантна раковина "Чистота"',
            'Стильна ванна "Релакс"',
            'Функціональний душ "Комфорт"',
            'Класичний унітаз "Традиція"',
            'Мінімалістична раковина "Стиль"',
            'Вікторіанська ванна "Розкіш"',
            'Скандинавський душ "Простір"',
            'Промисловий унітаз "Лофт"',
            'Сучасна ванна "Модерн"',
            
            # Побутова техніка
            'Надійний холодильник "Крижа"',
            'Надійна пральна машина "Чистота"',
            'Сучасна посудомийна машина "Практик"',
            'Елегантна духовка "Кулінарія"',
            'Стильна мікрохвильова піч "Швидкість"',
            'Класична кавоварка "Аромат"',
            'Мінімалістичний чайник "Тепло"',
            'Вікторіанський тостер "Традиція"',
            'Скандинавський блендер "Здоров\'я"',
            'Промисловий міксер "Потужність"',
            
            # Кухонні прилади
            'Сучасна миска "Практик"',
            'Елегантний набір ножів "Кулінарія"',
            'Стильна сковорода "Смак"',
            'Класичний казан "Традиція"',
            'Мінімалістичний блендер "Здоров\'я"',
            'Вікторіанська форма для випічки "Розкіш"',
            'Скандинавський набір ложок "Простір"',
            'Промисловий міксер "Потужність"',
            'Сучасний чайник "Тепло"',
            'Елегантна кавоварка "Аромат"',
        ]
        
        products = []
        for i in range(count):
            # Якщо назв менше ніж потрібно товарів, створюємо варіації
            if i < len(product_names):
                title = product_names[i]
            else:
                # Створюємо варіації існуючих назв
                base_name = product_names[i % len(product_names)]
                variation_suffixes = ['Pro', 'Plus', 'Premium', 'Elite', 'Ultra', 'Max', 'Deluxe', 'Exclusive']
                suffix = variation_suffixes[i // len(product_names)]
                title = f"{base_name} {suffix}"
            
            product = Product.objects.create(
                title=title,
                description=f'Опис для товару "{title}". Якісний товар для вашого дому.',
                is_new=random.choice([True, False]),
                has_discount=random.choice([True, False]),
                meta_title=f"{title} - Купити онлайн",
                meta_description=f"Купити {title} за найкращою ціною. Доставка по всій Україні."
            )
            
            # Додаємо категорії
            category = random.choice(categories)
            product.categories.add(category)
            
            # Додаємо кольори
            product_colors = random.sample(list(colors), random.randint(1, 3))
            product.colors.add(*product_colors)
            
            products.append(product)
            self.stdout.write(f'Створено товар: {product.title}')
        
        return products

    def create_product_attributes(self, products, sizes, widths):
        """Створює атрибути товарів"""
        for product in products:
            # Створюємо кілька варіацій для кожного товару
            num_variations = random.randint(2, 6)
            
            for i in range(num_variations):
                size = random.choice(sizes) if random.choice([True, False]) else None
                price = random.randint(500, 5000)
                quantity = random.randint(1, 50)
                discount = random.randint(0, 30) if random.choice([True, False]) else None
                
                attr = ProductAttribute.objects.create(
                    product=product,
                    size=size,
                    price=price,
                    quantity=quantity,
                    discount=discount,
                    custom_attribute=random.choice([True, False])
                )
                
                # Додаємо ширини для кастомних варіацій
                if attr.custom_attribute:
                    attr.min_len = Decimal(str(random.randint(50, 200)))
                    attr.max_len = Decimal(str(random.randint(200, 500)))
                    attr.custom_price = Decimal(str(random.randint(100, 1000)))
                    attr.width.set(random.sample(list(widths), random.randint(1, 3)))
                    attr.save()
                
                self.stdout.write(f'  - Створено атрибут: {attr}')

    def create_product_specifications(self, products, specifications):
        """Створює специфікації товарів"""
        for product in products:
            # Додаємо 3-5 специфікацій для кожного товару
            product_specs = random.sample(list(specifications), random.randint(3, 5))
            
            for spec in product_specs:
                # Отримуємо всі значення специфікацій
                all_values = SpecificationValue.objects.all()
                if all_values.exists():
                    spec_value = random.choice(all_values)
                    ProductSpecification.objects.create(
                        product=product,
                        specification=spec,
                        spec_value=spec_value
                    )
                    self.stdout.write(f'  - Додано специфікацію: {spec.title} = {spec_value.title}')

    def create_reviews(self, products):
        """Створює відгуки на товари"""
        names = ['Олена', 'Іван', 'Марія', 'Петро', 'Анна', 'Михайло', 'Тетяна', 'Олександр', 'Катерина', 'Дмитро', 'Юлія', 'Андрій', 'Наталія', 'Віктор', 'Ірина', 'Сергій']
        reviews_text = [
            'Дуже якісний товар, рекомендую!',
            'Відповідає опису, задоволений покупкою.',
            'Швидка доставка, товар як на фото.',
            'Відмінна якість за таку ціну.',
            'Дуже зручно користуватися.',
            'Краще ніж очікував.',
            'Гарний товар, але трохи дорогий.',
            'Рекомендую всім друзям.',
            'Відмінний вибір для дому!',
            'Якість на висоті, ціна прийнятна.',
            'Дуже задоволений покупкою.',
            'Товар перевершив очікування.',
            'Швидко доставили, все якісно.',
            'Варто своїх грошей.',
            'Дуже практичний товар.',
            'Стильний дизайн, якісне виконання.',
        ]
        
        for product in products:
            # Створюємо 2-5 відгуків для кожного товару
            num_reviews = random.randint(2, 5)
            for _ in range(num_reviews):
                ProductReview.objects.create(
                    product=product,
                    name=random.choice(names),
                    content=random.choice(reviews_text),
                    rating=random.randint(3, 5)
                )
                self.stdout.write(f'  - Створено відгук для: {product.title}')

    def create_sales(self, products):
        """Створює акції"""
        # Перевіряємо, чи вже існує головна акція
        existing_main_sale = ProductSale.objects.filter(main_sale=True).exists()
        
        # Створюємо кілька акцій
        num_sales = random.randint(3, 6)
        for i in range(num_sales):
            # Якщо вже є головна акція, не створюємо ще одну
            if existing_main_sale and i == 0:
                main_sale = False
            else:
                main_sale = random.choice([True, False]) if not existing_main_sale else False
            
            # Якщо це головна акція, позначаємо що вона вже існує
            if main_sale:
                existing_main_sale = True
            
            try:
                sale_products = random.sample(list(products), random.randint(5, 12))
                
                sale = ProductSale.objects.create(
                    date_end=timezone.now() + timedelta(days=random.randint(7, 30)),
                    main_sale=main_sale
                )
                sale.products.set(sale_products)
                
                self.stdout.write(f'Створено акцію з {len(sale_products)} товарами (main_sale={main_sale})')
            except Exception as e:
                self.stdout.write(f'Помилка створення акції: {e}')
                continue

    def create_promocodes(self):
        """Створює промокоди"""
        promocodes_data = [
            {'code': 'WELCOME10', 'discount': 10},
            {'code': 'SUMMER20', 'discount': 20},
            {'code': 'NEWYEAR15', 'discount': 15},
            {'code': 'SALE25', 'discount': 25},
            {'code': 'SPRING30', 'discount': 30},
            {'code': 'AUTUMN15', 'discount': 15},
            {'code': 'WINTER40', 'discount': 40},
            {'code': 'HOLIDAY50', 'discount': 50},
            {'code': 'VIP20', 'discount': 20},
            {'code': 'FIRST5', 'discount': 5},
        ]
        
        for promo_data in promocodes_data:
            PromoCode.objects.create(
                code=promo_data['code'],
                discount=promo_data['discount'],
                end_time=timezone.now() + timedelta(days=random.randint(30, 90))
            )
            self.stdout.write(f'Створено промокод: {promo_data["code"]} ({promo_data["discount"]}%)') 