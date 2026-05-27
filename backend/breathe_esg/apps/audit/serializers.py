from rest_framework import serializers, generics
from rest_framework.permissions import IsAuthenticated
from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id", "action", "action_display", "actor_email",
            "emission_record", "ingestion_batch",
            "previous_value", "new_value", "note", "created_at",
        ]

    def get_actor_email(self, obj):
        return obj.actor.email if obj.actor else "system"


class AuditEventListView(generics.ListAPIView):
    serializer_class = AuditEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = AuditEvent.objects.filter(organisation=self.request.user.organisation)
        record_id = self.request.query_params.get("record")
        if record_id:
            qs = qs.filter(emission_record_id=record_id)
        return qs
