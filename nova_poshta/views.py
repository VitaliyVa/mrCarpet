import logging

from django.conf import settings
from django.db.models import Q, Case, When, IntegerField
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination

from .models import Warehouse, Settlement
from .serializers import (
    WarehouseSerializer,
    SettlementSerializer,
)

logger = logging.getLogger("nova_poshta.api")


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000


class WarehousesList(generics.ListAPIView):
    serializer_class = WarehouseSerializer
    queryset = Warehouse.objects.all()
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        query = self.request.query_params.get("q")
        logger.info(
            "warehouses q=%r type=%s settlement_total=%s warehouse_total=%s",
            query,
            type(query).__name__,
            Settlement.objects.count(),
            Warehouse.objects.count(),
        )

        if not query:
            logger.warning("warehouses: empty q → none()")
            return Warehouse.objects.none()

        # Килими не влізають у поштомати — не показуємо їх у чекауті
        postomat_q = Q(type__title__icontains="поштомат") | Q(
            title__icontains="поштомат"
        )

        try:
            settlement_id = int(query)
            qs = self.queryset.filter(settlement_id=settlement_id).exclude(
                postomat_q
            )
            logger.info(
                "warehouses: filter by settlement_id=%s → %s",
                settlement_id,
                qs.count(),
            )
            return qs
        except (TypeError, ValueError):
            qs = self.queryset.filter(settlement__ref=query).exclude(postomat_q)
            logger.info(
                "warehouses: filter by settlement__ref=%r → %s",
                query,
                qs.count(),
            )
            return qs


class SettlementsList(generics.ListAPIView):
    serializer_class = SettlementSerializer
    queryset = Settlement.objects.all()
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        raw_q = self.request.query_params.get("q")
        # Also peek GET in case of odd parsing
        get_q = self.request.GET.get("q")
        db_engine = settings.DATABASES["default"]["ENGINE"]
        total = Settlement.objects.count()

        logger.info(
            "settlements request path=%s raw_q=%r get_q=%r equal=%s "
            "codepoints=%s engine=%s settlement_total=%s",
            self.request.get_full_path(),
            raw_q,
            get_q,
            raw_q == get_q,
            [hex(ord(c)) for c in (raw_q or "")],
            db_engine,
            total,
        )

        query = (raw_q or "").strip()
        if not query:
            logger.warning("settlements: empty/missing q → none()")
            return Settlement.objects.none()

        # SQLite: icontains is ASCII-case-insensitive only — Cyrillic case matters.
        # Log both original and title-cased variants for diagnosis.
        folded = query[:1].upper() + query[1:] if query else query
        exact_n = Settlement.objects.filter(title__iexact=query).count()
        start_n = Settlement.objects.filter(title__istartswith=query).count()
        contain_n = Settlement.objects.filter(title__icontains=query).count()
        folded_n = Settlement.objects.filter(title__icontains=folded).count()
        # Direct exact (case-sensitive) — useful if DB has «Київ» but q is «київ»
        cs_exact = Settlement.objects.filter(title=query).count()
        cs_folded = Settlement.objects.filter(title=folded).count()

        logger.info(
            "settlements match q=%r folded=%r "
            "iexact=%s istartswith=%s icontains=%s "
            "icontains_folded=%s exact_cs=%s folded_cs=%s",
            query,
            folded,
            exact_n,
            start_n,
            contain_n,
            folded_n,
            cs_exact,
            cs_folded,
        )

        queryset = self.queryset.filter(
            Q(title__iexact=query)
            | Q(title__istartswith=query)
            | Q(title__icontains=query)
            | Q(title__iexact=folded)
            | Q(title__istartswith=folded)
            | Q(title__icontains=folded)
        ).annotate(
            priority=Case(
                When(title__iexact=query, then=0),
                When(title__iexact=folded, then=0),
                When(title__istartswith=query, then=1),
                When(title__istartswith=folded, then=1),
                When(title__icontains=query, then=2),
                When(title__icontains=folded, then=2),
                default=999,
                output_field=IntegerField(),
            ),
        ).order_by("priority", "title")

        final_n = queryset.count()
        sample = list(queryset.values_list("id", "title")[:5])
        logger.info(
            "settlements result_count=%s sample=%s",
            final_n,
            sample,
        )
        if final_n == 0 and total > 0:
            logger.error(
                "settlements: ZERO hits while DB has %s rows — "
                "check encoding of q or empty/wrong DB sync (manage.py np)",
                total,
            )
        elif total == 0:
            logger.error(
                "settlements: Settlement table EMPTY — run nova_poshta sync "
                "(management command np)"
            )
        return queryset
