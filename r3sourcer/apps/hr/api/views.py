from rest_framework.response import Response
from rest_framework.views import APIView

from r3sourcer.apps.candidate import models as candidate_models
from r3sourcer.apps.core import models as core_models
from r3sourcer.apps.hr import models as hr_models
from r3sourcer.apps.hr.utils import job as job_utils
from r3sourcer.apps.hr.utils.utils import calculate_distances_for_jobsite


class CandidateDistanceView(APIView):

    def post(self, request, *args, **kwargs):
        job = request.data.get('job', None)
        candidate_contacts = request.data.get('candidates', [])
        if not isinstance(candidate_contacts, list):
            candidate_contacts = [candidate_contacts]
        distances = []
        if job and candidate_contacts:
            job = hr_models.Job.objects.get(id=job)
            contacts = core_models.Contact.objects.filter(candidate_contacts__id__in=candidate_contacts)
            calculate_distances_for_jobsite(contacts, job.jobsite)

        for candidate in candidate_models.CandidateContact.objects.filter(id__in=candidate_contacts):
            matrix = job.get_distance_matrix(candidate)
            if matrix:
                distances.append({'contact': candidate.id, **matrix})

        return Response(distances)


class AvailableCandidatesDateView(APIView):

    def post(self, request, *args, **kwargs):
        job = request.data.get("job", None)
        shifts = request.data.get("shifts", None)
        result = []
        if job:
            job = hr_models.Job.objects.get(pk=job)
            job_shifts = hr_models.Shift.objects.filter(id__in=shifts, date__job=job)
            candidate_contacts = job_utils.get_available_candidate_list(job)

            partially_available = job_utils.get_partially_available_candidate_ids(
                candidate_contacts, job_shifts
            )
            result = [
                partial for partial, data in partially_available.items()
                if len(data['shifts']) == job_shifts.count()
            ]
        return Response({'result': result})
