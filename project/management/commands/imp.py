import tablib
import os

from pathlib import Path
from django.core.management.base import BaseCommand
from django.contrib.sessions.models import Session
from django.contrib.auth.models import Permission, Group
from django.contrib.contenttypes.models import ContentType
from django.contrib.admin.models import LogEntry

from .logging import ImportLogger
from .utils import ResourceGenerator, ModelSorter, get_file_path

from order.models import Order
from cart.models import Cart, CartProduct


logger = ImportLogger(base_path=Path(os.path.dirname(os.path.realpath(__file__))))


class Command(BaseCommand):
    help = "python manage.py imp -path export -format csv"

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default="project/export",
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
            logger.info(f"{model.__name__}")
            file_path = get_file_path(model, kwargs["path"])
            resource = ResourceGenerator.get_resource(model)
            dataset = tablib.Dataset()
            if os.path.exists(file_path):
                with open(file_path, "r", newline="", encoding="utf-8") as file:
                    dataset.load(file.read(), format="csv")
                    resource.import_data(dataset, raise_errors=True)
            logger.info(f"{model.__name__} Success!\n")