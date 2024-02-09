from django.core.management.base import BaseCommand
from .utils import ResourceGenerator, ModelSorter, get_file_path, get_folder_path

from django.contrib.sessions.models import Session
from django.contrib.auth.models import Permission, Group
from django.contrib.contenttypes.models import ContentType
from django.contrib.admin.models import LogEntry

from order.models import Order
from cart.models import Cart, CartProduct


class Command(BaseCommand):
    help = "python manage.py exp -path export -format csv"

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            default="project/export",
            nargs="?",
            help="path will be created within base_dir",
        )

    def handle(self, *args, **kwargs):
        exclude_models = [
            Session,
            Permission,
            Group,
            ContentType,
            LogEntry,
            Order,
            Cart,
            CartProduct,
        ]
        models = ModelSorter.sort_models(exclude_models=exclude_models)
        for model in models:
            folder_path = get_folder_path(model, kwargs["path"])
            file_path = get_file_path(model, kwargs["path"])
            folder_path.mkdir(parents=True, exist_ok=True)
            resource = ResourceGenerator.get_resource(model)
            data = resource.export().csv
            with open(file_path, "w", newline="", encoding="utf8") as file:
                file.write(data)
            print(f"{model.__name__:<25} Success!")