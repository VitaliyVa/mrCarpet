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
            default=5,
            help='Кількість категорій для створення (за замовчуванням: 5)'
        )
        parser.add_argument(
            '--products',
            type=int,
            default=20,
            help='Кількість товарів для створення (за замовчуванням: 20)'
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
            'Маленький', 'Середній', 'Великий', 'Дуже великий',
            '50x50', '100x100', '150x150', '200x200', '250x250',
            'S', 'M', 'L', 'XL', 'XXL'
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
                'values': ['Червоний', 'Синій', 'Зелений', 'Чорний', 'Білий', 'Сірий']
            },
            {
                'title': 'Матеріал',
                'values': ['Шерсть', 'Бавовна', 'Поліестер', 'Шовк', 'Льон', 'Акрил']
            },
            {
                'title': 'Стиль',
                'values': ['Класичний', 'Сучасний', 'Мінімалізм', 'Вікторіанський', 'Скандинавський']
            },
            {
                'title': 'Тип',
                'values': ['Килим', 'Покриття', 'Декор', 'Меблі', 'Освітлення']
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
            'Елегантний килим "Комфорт"',
            'Сучасне покриття "Модерн"',
            'Декоративна подушка "Стиль"',
            'Комфортне крісло "Релакс"',
            'Стильний світильник "Світло"',
            'Якісна скатертина "Елеганс"',
            'Сучасна миска "Практик"',
            'Надійний холодильник "Крижа"',
            'Елегантний диван "Комфорт Плюс"',
            'Стильний стіл "Модерн"',
            'Якісний килим "Традиція"',
            'Сучасне покриття "Інновація"',
            'Декоративна ваза "Арт"',
            'Комфортне ліжко "Сон"',
            'Стильна лампа "Освітлення"',
            'Якісна ковдра "Тепло"',
            'Сучасний унітаз "Гігієна"',
            'Надійна пральна машина "Чистота"',
            'Елегантний шкаф "Організація"',
            'Стильний стілець "Ергономіка"',
        ]
        
        products = []
        for i in range(min(count, len(product_names))):
            product = Product.objects.create(
                title=product_names[i],
                description=f'Опис для товару "{product_names[i]}". Якісний товар для вашого дому.',
                is_new=random.choice([True, False]),
                has_discount=random.choice([True, False]),
                meta_title=f"{product_names[i]} - Купити онлайн",
                meta_description=f"Купити {product_names[i]} за найкращою ціною. Доставка по всій Україні."
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
            num_variations = random.randint(1, 4)
            
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
            # Додаємо 2-3 специфікації для кожного товару
            product_specs = random.sample(list(specifications), random.randint(2, 3))
            
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
        names = ['Олена', 'Іван', 'Марія', 'Петро', 'Анна', 'Михайло', 'Тетяна', 'Олександр']
        reviews_text = [
            'Дуже якісний товар, рекомендую!',
            'Відповідає опису, задоволений покупкою.',
            'Швидка доставка, товар як на фото.',
            'Відмінна якість за таку ціну.',
            'Дуже зручно користуватися.',
            'Краще ніж очікував.',
            'Гарний товар, але трохи дорогий.',
            'Рекомендую всім друзям.',
        ]
        
        for product in products:
            # Створюємо 1-3 відгуки для кожного товару
            num_reviews = random.randint(1, 3)
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
        sale_products = random.sample(list(products), random.randint(3, 8))
        
        sale = ProductSale.objects.create(
            date_end=timezone.now() + timedelta(days=random.randint(7, 30)),
            main_sale=random.choice([True, False])
        )
        sale.products.set(sale_products)
        
        self.stdout.write(f'Створено акцію з {len(sale_products)} товарами')

    def create_promocodes(self):
        """Створює промокоди"""
        promocodes_data = [
            {'code': 'WELCOME10', 'discount': 10},
            {'code': 'SUMMER20', 'discount': 20},
            {'code': 'NEWYEAR15', 'discount': 15},
            {'code': 'SALE25', 'discount': 25},
        ]
        
        for promo_data in promocodes_data:
            PromoCode.objects.create(
                code=promo_data['code'],
                discount=promo_data['discount'],
                end_time=timezone.now() + timedelta(days=random.randint(30, 90))
            )
            self.stdout.write(f'Створено промокод: {promo_data["code"]} ({promo_data["discount"]}%)') 