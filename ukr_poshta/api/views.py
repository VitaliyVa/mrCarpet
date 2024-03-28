from rest_framework import status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from .serializers import CitySerializer
from ..models import City
from ..utils import get_office


class UkrposhtaViewSet(ViewSet):
    pagination_class = PageNumberPagination

    def list(self, request):
        city_id = request.GET.get("city_id")
        offices = get_office(city_id)
        paginator = PageNumberPagination()
        paginator.page_size = 10
        paginated_queryset = paginator.paginate_queryset(offices, request)
        if not offices:
            return Response(
                {"message": "error"},
                status=status.HTTP_400_BAD_REQUEST
            )
        return Response({
            'count': paginator.page.paginator.count,
            'next': paginator.get_next_link(),
            'previous': paginator.get_previous_link(),
            'results': paginated_queryset
        })

    @action(detail=False, methods=["get"])
    def base_offices(self, request):
        try:
            city_name = int(request.GET.get("city_id"))
            if city_name:
                print("good")
                city = City.objects.get(city_id=city_name)
                serializer = CitySerializer(instance=city)
                print(len(serializer.data["offices"]))
                return Response(
                    serializer.data,
                    status=status.HTTP_200_OK
                )
            return Response(
                {"message": "Id не коректне!"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"message": "".join(str(e))},
                status=status.HTTP_400_BAD_REQUEST
            )
