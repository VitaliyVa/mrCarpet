import os
import types

from pathlib import Path
from import_export import resources, fields
from import_export.widgets import ManyToManyWidget
from import_export.resources import ModelResource, ModelDeclarativeMetaclass
from import_export.results import RowResult
from django.conf import settings
from django.apps import apps
from django.db.models import Model
from django.db.models.fields import Field
from dataclasses import dataclass, field

from typing import List, Optional, Union

from .logging import ImportLogger


logger = ImportLogger(base_path=Path(os.path.dirname(os.path.realpath(__file__))))


def get_file_path(
    model: Model, path: Union[str, os.PathLike], dot_type: str = ".csv"
) -> os.PathLike:
    label = model._meta.label
    folder_label = label[: label.rfind(".")]
    file_name = label[label.rfind(".") + 1 :] + dot_type
    file_path = Path(settings.BASE_DIR) / path / folder_label / file_name
    return file_path


def get_folder_path(model: Model, path: Union[str, os.PathLike]) -> os.PathLike:
    label = model._meta.label
    folder_label = label[: label.rfind(".")]
    folder_path = Path(settings.BASE_DIR) / path / folder_label
    return folder_path


def get_field_names(self):
    names = []
    for field in self.get_fields():
        names.append(self.get_field_name(field))
    return names


def import_row(self, row, instance_loader, **kwargs):
    import_result = super(ModelResource, self).import_row(
        row, instance_loader, **kwargs
    )
    if import_result.import_type == RowResult.IMPORT_TYPE_ERROR:
        import_result.diff = [row.get(name, "") for name in self.get_field_names()]
        import_result.diff.append(
            "Errors: {}".format([err.error for err in import_result.errors])
        )
        import_result.errors = []
        import_result.import_type = RowResult.IMPORT_TYPE_SKIP
    return import_result


def after_import(self, dataset, result, using_transactions, dry_run, **kwargs):
    total_skipped = 0
    for row in result.rows:
        if "Errors: " in row.diff[-1]:
            total_skipped += 1
            logger.info(row.diff[-1])
    logger.info(f"Imported: {result.total_rows - total_skipped} of {result.total_rows}")
    return super(ModelResource, self).after_import(
        dataset, result, using_transactions, dry_run, **kwargs
    )


def modelresource_factory(model, resource_class=ModelResource):
    attrs = {"model": model}
    Meta = type(str("Meta"), (object,), attrs)

    class_name = model.__name__ + str("Resource")

    class_attrs = {
        "Meta": Meta,
    }

    metaclass = ModelDeclarativeMetaclass(class_name, (resource_class,), class_attrs)
    setattr(metaclass, "get_field_names", get_field_names)
    setattr(metaclass, "import_row", import_row)
    setattr(metaclass, "after_import", after_import)
    return metaclass


class ResourceGenerator:
    @staticmethod
    def set_m2m_fields(model: Model, resource: resources.ModelResource):
        resource.Meta.fields = []
        resource.Meta.model = model
        concrete_fields = model._meta.concrete_fields
        for field in model._meta.get_fields():
            if field in concrete_fields:
                if field.many_to_many:
                    resource.Meta.fields.append(field.name)
                    related_model = field.related_model
                    setattr(
                        resource,
                        field.name,
                        fields.Field(widget=ManyToManyWidget(related_model)),
                    )

    @classmethod
    def get_resource(cls, model: Model) -> resources.ModelResource:
        resource = modelresource_factory(model)
        cls.set_m2m_fields(model, resource)
        return resource()


@dataclass
class ModelProp:
    model: Model
    model_fields: List[Field] = field(init=False)
    one_to_many: bool = False
    one_to_one: bool = False
    many_to_one: bool = False
    many_to_many: bool = False
    relation: bool = False
    position: int = 1

    def set_relation(self) -> bool:
        self.relation = any([f.is_relation for f in self.model_fields])
        if self.many_to_many or self.one_to_one and not self.one_to_many and not self.many_to_one:
            self.relation = False
        if self.one_to_many and not self.many_to_one:
            self.relation = False

    def __post_init__(self):
        self.model_fields = self.model._meta.get_fields()
        self.one_to_many = any([f.one_to_many for f in self.model_fields])
        self.one_to_one = any([f.one_to_one for f in self.model_fields])
        self.many_to_one = any([f.many_to_one for f in self.model_fields])
        self.many_to_many = any([f.many_to_many for f in self.model_fields])
        self.set_relation()


@dataclass
class UltimatePropList:
    models: List[Model]
    model_props: List[ModelProp] = field(init=False)
    without_relation: List[ModelProp] = field(init=False, default_factory=list)
    origin_models: List[ModelProp] = field(init=False, default_factory=list)
    model_prop_chains: List[List[ModelProp]] = field(init=False, default_factory=list)
    all_model_props: List[ModelProp] = field(init=False, default_factory=list)

    def __post_init__(self):
        self.model_props = [ModelProp(model) for model in apps.get_models()]
        self.without_relation = self.get_without_relation()
        self.origin_models = self.get_origin_models()
        self.model_prop_chains = self.get_model_prop_chains()
        self.all_model_props = self.get_all_model_props()

    def get_without_relation(self) -> List[ModelProp]:
        for model_prop in self.model_props:
            if model_prop.relation is False:
                self.without_relation.append(model_prop)
        return self.without_relation

    def get_origin_models(self) -> List[ModelProp]:
        for model_prop in self.model_props:
            if model_prop.one_to_many is True and model_prop.many_to_one is False:
                self.origin_models.append(model_prop)
        return self.origin_models

    def get_model_prop_chains(self) -> List[ModelProp]:
        for zero_model in self.origin_models:
            for chain in ModelPropChainBuilder.build_chain(
                self.model_props, next_models=[zero_model]
            ):
                self.model_prop_chains.append(chain)
        return self.model_prop_chains

    def get_all_model_props(self) -> List[ModelProp]:
        for chain in self.model_prop_chains:
            for model_prop in chain:
                self.all_model_props.append(model_prop)
        return self.all_model_props

    def get_sorted_props(self) -> List[ModelProp]:
        key = lambda x: x.position
        _sorted = []
        [_sorted.append(x) for x in self.origin_models if x not in _sorted]
        [_sorted.append(x) for x in self.without_relation if x not in _sorted]
        srt = sorted(self.all_model_props, key=key)
        [_sorted.append(x) for x in srt if x not in _sorted]
        return _sorted

    def get_sorted_models(self):
        return [mp.model for mp in self.get_sorted_props()]


class ModelPropChainBuilder:
    "Build a chain of ModelProp instances with appropriate position parameter"

    @staticmethod
    def get_next_models(
        models_props: List[ModelProp],
        next_models: List[ModelProp],
        counter: int,
        chains: List[List[ModelProp]],
    ):
        models = [model.model for model in next_models]
        next_models = []
        for model in models:
            for field in model._meta.get_fields():
                if field.one_to_many:
                    gen = (x for x in models_props if x.model == field.related_model)
                    next_models.append(next(gen))
        for model_prop in next_models:
            model_prop.position = counter
        if next_models not in chains:
            return next_models
        else:
            return []

    @classmethod
    def build_chain(
        cls,
        models_props: List[ModelProp],
        next_models: List = list(),
        chains: List = list(),
        counter: int = 1,
    ) -> List[ModelProp]:
        """Be aware, there is recursion"""
        counter += 1
        next_models = cls.get_next_models(models_props, next_models, counter, chains)
        if not next_models:
            return chains
        else:
            chains.append(next_models)
            return cls.build_chain(
                models_props, next_models=next_models, chains=chains, counter=counter
            )


class ModelSorter:
    @classmethod
    def sort_models(
        cls,
        *,
        models: Optional[List[Model]] = None,
        exclude_models: Optional[List[Model]] = None,
    ):
        models = models or apps.get_models()
        sorted_models = UltimatePropList(models).get_sorted_models()
        if exclude_models:
            return [m for m in sorted_models if m not in exclude_models]
        return sorted_models