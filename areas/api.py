# The REST API (Django REST Framework).
#
#   GET /api/score/?address=Navrangpura, Ahmedabad   score any address (rate limited)
#   GET /api/score/?lat=23.03&lon=72.56               score coordinates
#   GET /api/suggest/?q=koramangla                    typo-tolerant suggestions while typing
#   GET /api/areas/                                  every scored area, best first
#   GET /api/areas/?search=ahmedabad                 filter by name
#   GET /api/areas/<id>/                             one area with its breakdown and places

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from areas.models import Area
from areas.serializers import AreaDetailSerializer, AreaListSerializer
from areas.services.area_builder import score_address, score_coordinates
from areas.services.errors import AddressNotFound, MapServiceBusy
from areas.services.suggestions import suggest


class ScoreView(APIView):
    """Scores an address or a pair of coordinates."""

    # Scoring a new place calls free public map services, so limit how often it can be used
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "score"

    def get(self, request):
        address_text = request.query_params.get("address", "").strip()
        latitude_text = request.query_params.get("lat")
        longitude_text = request.query_params.get("lon")

        try:
            if address_text != "":
                area = score_address(address_text)
            elif latitude_text is not None and longitude_text is not None:
                area = score_coordinates(float(latitude_text), float(longitude_text))
            else:
                return Response({"error": "Send ?address=... or ?lat=...&lon=..."},
                                status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({"error": "lat and lon must be numbers."},
                            status=status.HTTP_400_BAD_REQUEST)
        except AddressNotFound as error:
            return Response({"error": str(error)}, status=status.HTTP_404_NOT_FOUND)
        except MapServiceBusy as error:
            return Response({"error": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(AreaDetailSerializer(area).data)


class SuggestView(APIView):
    """Search suggestions while typing. ?local=1 returns only the instant database matches."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "suggest"

    def get(self, request):
        text = request.query_params.get("q", "")
        only_local = request.query_params.get("local") == "1"
        return Response({"results": suggest(text, include_photon=not only_local)})


class AreaListView(generics.ListAPIView):
    """Every scored area, best first. ?search= filters by name."""

    serializer_class = AreaListSerializer

    def get_queryset(self):
        queryset = Area.objects.order_by("-score", "name")
        search_text = self.request.query_params.get("search", "").strip()
        if search_text != "":
            queryset = queryset.filter(name__icontains=search_text)
        return queryset


class AreaDetailView(generics.RetrieveAPIView):
    """One area with its category breakdown and every place on its map."""

    queryset = Area.objects.prefetch_related("category_scores", "places")
    serializer_class = AreaDetailSerializer
