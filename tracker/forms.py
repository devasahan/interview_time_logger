from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Q

from accounts.models import TeamRole

from .models import Interview, InterviewType, validate_time_slot, validate_work_date
from .periods import EARLIEST_DATE, LATEST_DATE


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%Y-%m-%d")


class TimeInput(forms.TimeInput):
    input_type = "time"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%H:%M")


class TimedEntryForm(forms.ModelForm):
    """A date and a time range: interviews and developer work."""

    kind = "work"
    required_fields = ("start_time", "end_time", "interview_with", "role")

    class Meta:
        model = Interview
        fields = ["date", "start_time", "end_time", "interview_with", "role", "notes"]
        widgets = {
            "date": DateInput(),
            "start_time": TimeInput(),
            "end_time": TimeInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        if self.instance.pk is None:
            self.instance.user = owner
        # Optional in the database (bid entries leave them empty) but needed here.
        for name in self.required_fields:
            self.fields[name].required = True

    def clean(self):
        cleaned = super().clean()
        day, start, end = cleaned.get("date"), cleaned.get("start_time"), cleaned.get("end_time")
        if day is not None and start is not None and end is not None:
            try:
                validate_time_slot(
                    user_id=self.owner.pk, day=day, start=start, end=end, exclude_pk=self.instance.pk, kind=self.kind
                )
            except ValidationError as error:
                self.add_error(None, error)
        return cleaned


class InterviewForm(TimedEntryForm):
    kind = "interview"
    required_fields = TimedEntryForm.required_fields + ("interview_type",)

    class Meta(TimedEntryForm.Meta):
        fields = ["date", "start_time", "end_time", "interview_with", "role", "interview_type", "notes"]
        labels = {
            "start_time": "From",
            "end_time": "To",
            "interview_with": "Interview with",
            "role": "Role",
        }
        help_texts = {
            "interview_with": "The company or person you interviewed with.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Offer active types, plus the current one when editing an older entry.
        available = Q(is_active=True)
        if self.instance.interview_type_id:
            available |= Q(pk=self.instance.interview_type_id)
        self.fields["interview_type"].queryset = InterviewType.objects.filter(available)
        self.fields["interview_type"].empty_label = "Choose a type"
        self.fields["interview_with"].widget.attrs["placeholder"] = "e.g. Acme Corp or Jane Smith"
        self.fields["role"].widget.attrs["placeholder"] = "e.g. Senior Backend Engineer"


class WorkForm(TimedEntryForm):
    """Developers log time on a project; the project and task reuse the interview fields."""

    class Meta(TimedEntryForm.Meta):
        labels = {"start_time": "From", "end_time": "To", "interview_with": "Project", "role": "Task"}
        help_texts = {"interview_with": "The client or project you worked on."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["interview_with"].widget.attrs["placeholder"] = "e.g. Acme website"
        self.fields["role"].widget.attrs["placeholder"] = "e.g. Build the sign-up page"


MAX_BIDS_PER_DAY = 10_000


class BidForm(forms.ModelForm):
    """Virtual assistants log how many bids they sent, once per day."""

    class Meta:
        model = Interview
        fields = ["date", "bids", "notes"]
        labels = {"bids": "Number of bids"}
        help_texts = {"bids": "How many bids you sent that day."}
        widgets = {"date": DateInput(), "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        if self.instance.pk is None:
            self.instance.user = owner
        bids = self.fields["bids"]
        bids.required = True
        bids.error_messages["required"] = "Enter how many bids you sent, for example 40."
        bids.widget.attrs.update({"min": 1, "max": MAX_BIDS_PER_DAY, "inputmode": "numeric", "placeholder": "e.g. 40"})

    def clean_bids(self):
        bids = self.cleaned_data["bids"]
        if bids < 1:
            raise ValidationError("Enter at least 1 bid.")
        if bids > MAX_BIDS_PER_DAY:
            raise ValidationError("That's more bids than fit in one day. Check the number.")
        return bids

    def clean(self):
        cleaned = super().clean()
        day = cleaned.get("date")
        if day is not None:
            try:
                validate_work_date(day, "bids")
            except ValidationError as error:
                self.add_error(None, error)
                return cleaned
            already = Interview.objects.filter(user=self.owner, date=day, bids__isnull=False).exclude(pk=self.instance.pk)
            if already.exists():
                self.add_error("date", f"You already logged bids for {day:%b} {day.day}. Edit that day instead.")
        return cleaned


def hourly_rate_field():
    return forms.DecimalField(
        label="Rate",
        max_digits=10,
        decimal_places=2,
        min_value=0,
        help_text="Per hour, or per bid for virtual assistants.",
        error_messages={"required": "Enter a rate, for example 20.00."},
    )


def team_role_field():
    return forms.ChoiceField(
        label="Role",
        choices=[("", "Choose a role")] + TeamRole.choices,
        error_messages={"required": "Choose a role, for example Interviewer."},
    )


class ApproveForm(forms.Form):
    """One-step approval from the Team page; the rate starts today."""

    team_role = team_role_field()
    rate = hourly_rate_field()


class RateForm(forms.Form):
    rate = hourly_rate_field()
    effective_from = forms.DateField(
        widget=DateInput(),
        validators=[MinValueValidator(EARLIEST_DATE), MaxValueValidator(LATEST_DATE)],
        help_text="Applies to unpaid work on or after this date. Paid work keeps the rate it was paid at.",
    )


class ApproveWithRateForm(RateForm):
    """Approval from the member's page: their role plus a rate from any date."""

    team_role = team_role_field()
    field_order = ["team_role", "rate", "effective_from"]


class RoleForm(forms.Form):
    team_role = team_role_field()


class PayoutForm(forms.Form):
    note = forms.CharField(
        label="Payment note",
        required=False,
        max_length=255,
        help_text="For your records, e.g. a transfer reference.",
    )
    interview_ids = forms.CharField(widget=forms.HiddenInput)
    expected_total = forms.DecimalField(widget=forms.HiddenInput, max_digits=14, decimal_places=2)

    def clean_interview_ids(self):
        try:
            ids = [int(part) for part in self.cleaned_data["interview_ids"].split(",") if part.strip()]
        except ValueError:
            raise ValidationError("Invalid selection.")
        if not ids:
            raise ValidationError("Nothing selected to pay.")
        return ids


class InterviewTypeForm(forms.ModelForm):
    class Meta:
        model = InterviewType
        fields = ["name", "is_active"]
        labels = {"is_active": "Available when logging interviews"}

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if InterviewType.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise ValidationError("That interview type already exists.")
        return name
