from django.db.models import Sum, Count, Q
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import EmissionRecord
from .serializers import EmissionRecordSerializer, EmissionRecordUpdateSerializer, SummarySerializer


def org_records(request):
    """Base queryset scoped to the analyst's organisation."""
    return EmissionRecord.objects.filter(organisation=request.user.organisation)


class EmissionRecordListView(generics.ListAPIView):
    serializer_class = EmissionRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = org_records(self.request)

        # Filters
        scope = self.request.query_params.get("scope")
        status_filter = self.request.query_params.get("status")
        source = self.request.query_params.get("source_type")
        year = self.request.query_params.get("year")
        search = self.request.query_params.get("search")

        if scope:
            qs = qs.filter(scope=scope)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if source:
            qs = qs.filter(source_type=source)
        if year:
            qs = qs.filter(reporting_year=year)
        if search:
            qs = qs.filter(
                Q(raw_description__icontains=search)
                | Q(facility_name__icontains=search)
                | Q(facility_code__icontains=search)
                | Q(sub_category__icontains=search)
            )
        return qs


class EmissionRecordDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return org_records(self.request)

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return EmissionRecordUpdateSerializer
        return EmissionRecordSerializer


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_record(request, pk):
    try:
        record = org_records(request).get(pk=pk)
    except EmissionRecord.DoesNotExist:
        return Response({"detail": "Not found."}, status=404)

    try:
        record.approve(request.user)
    except ValueError as e:
        return Response({"detail": str(e)}, status=400)

    return Response(EmissionRecordSerializer(record).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def flag_record(request, pk):
    try:
        record = org_records(request).get(pk=pk)
    except EmissionRecord.DoesNotExist:
        return Response({"detail": "Not found."}, status=404)

    note = request.data.get("note", "")
    try:
        record.flag(request.user, note=note)
    except ValueError as e:
        return Response({"detail": str(e)}, status=400)

    return Response(EmissionRecordSerializer(record).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bulk_approve(request):
    """Approve multiple records at once."""
    ids = request.data.get("ids", [])
    records = org_records(request).filter(pk__in=ids).exclude(status=EmissionRecord.STATUS_LOCKED)
    count = records.count()
    for r in records:
        r.approve(request.user)
    return Response({"approved": count})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def summary(request):
    """Aggregate summary by scope for the dashboard."""
    year = request.query_params.get("year", request.user.organisation.active_reporting_year)
    qs = org_records(request).filter(reporting_year=year)

    scope_labels = {
        EmissionRecord.SCOPE_1: "Scope 1 – Direct",
        EmissionRecord.SCOPE_2: "Scope 2 – Electricity",
        EmissionRecord.SCOPE_3: "Scope 3 – Value chain",
    }

    result = []
    for scope_val in [EmissionRecord.SCOPE_1, EmissionRecord.SCOPE_2, EmissionRecord.SCOPE_3]:
        scope_qs = qs.filter(scope=scope_val)
        agg = scope_qs.aggregate(
            total=Sum("kg_co2e"),
            total_count=Count("id"),
            pending=Count("id", filter=Q(status=EmissionRecord.STATUS_PENDING)),
            approved=Count("id", filter=Q(status=EmissionRecord.STATUS_APPROVED)),
            flagged=Count("id", filter=Q(status=EmissionRecord.STATUS_FLAGGED)),
        )
        result.append(
            {
                "scope": scope_val,
                "scope_display": scope_labels[scope_val],
                "total_kg_co2e": agg["total"] or 0,
                "record_count": agg["total_count"],
                "pending_count": agg["pending"],
                "approved_count": agg["approved"],
                "flagged_count": agg["flagged"],
            }
        )

    # Source breakdown
    source_breakdown = []
    for source_val, source_label in EmissionRecord.SOURCE_CHOICES:
        src_qs = qs.filter(source_type=source_val)
        agg = src_qs.aggregate(total=Sum("kg_co2e"), count=Count("id"))
        source_breakdown.append({
            "source": source_val,
            "label": source_label,
            "total_kg_co2e": agg["total"] or 0,
            "count": agg["count"],
        })

    return Response({
        "year": year,
        "by_scope": result,
        "by_source": source_breakdown,
        "total_kg_co2e": sum(r["total_kg_co2e"] for r in result),
        "pending_count": sum(r["pending_count"] for r in result),
    })
