from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from r3sourcer.apps.skills.models import SkillBaseRate, Skill


class MakeSkillBaseRateDefaultView(APIView):
    def post(self, *args, **kwargs):
        rate = get_object_or_404(SkillBaseRate, id=self.kwargs['id'])
        SkillBaseRate.objects.all().update(default_rate=False)
        rate.default_rate = True
        rate.save()
        return Response()


class SkillDefaultRateView(APIView):
    def post(self, *args, **kwargs):
        skill = get_object_or_404(Skill, id=self.kwargs['id'])
        price_list_default_rate = self.request.data.get("price_list_default_rate")
        if price_list_default_rate:
            skill.price_list_default_rate = price_list_default_rate
            skill.save(update_fields=['price_list_default_rate'])
        default_rate = self.request.data.get("default_rate")
        if default_rate:
            skill.default_rate = default_rate
            skill.save(update_fields=['default_rate'])
        active = self.request.data.get("active")
        if active is not None:
            skill.active = active
            skill.save(update_fields=['active'])
        return Response()
