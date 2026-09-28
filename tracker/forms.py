from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Q

from .models import Interview, InterviewType, validate_time_slot
from .periods import EARLIEST_DATE, LATEST_DATE


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%Y-%m-%d")


class TimeInput(forms.TimeInput):
    input_type = "time"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%H:%M")


class InterviewForm(forms.ModelForm):
    class Meta:
        model = Interview
        fields = ["date", "start_time", "end_time", "interview_with", "role", "interview_type", "notes"]
        labels = {
            "start_time": "From",
            "end_time": "To",
            "interview_with": "Interview with",
            "role": "Role",
        }
        help_texts = {
            "interview_with": "The company or person you interviewed with.",
            "end_time": "Ran past midnight? Just enter the end time; it counts as the next day.",
        }
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

        # Offer active types, plus the current one when editing an older entry.
        available = Q(is_active=True)
        if self.instance.interview_type_id:
            available |= Q(pk=self.instance.interview_type_id)
        self.fields["interview_type"].queryset = InterviewType.objects.filter(available)
        self.fields["interview_type"].empty_label = "Choose a type"
        self.fields["interview_with"].widget.attrs["placeholder"] = "e.g. Acme Corp or Jane Smith"
        self.fields["role"].widget.attrs["placeholder"] = "e.g. Senior Backend Engineer"

    def clean(self):
        cleaned = super().clean()
        day, start, end = cleaned.get("date"), cleaned.get("start_time"), cleaned.get("end_time")
        if day is not None and start is not None and end is not None:
            try:
                validate_time_slot(
                    user_id=self.owner.pk, day=day, start=start, end=end, exclude_pk=self.instance.pk
                )
            except ValidationError as error:
                self.add_error(None, error)
        return cleaned


def hourly_rate_field():
    return forms.DecimalField(
        label="Hourly rate",
        max_digits=10,
        decimal_places=2,
        min_value=0,
        error_messages={"required": "Enter an hourly rate, for example 20.00."},
    )


class ApproveForm(forms.Form):
    """One-step approval from the Team page; the rate starts today."""

    rate = hourly_rate_field()


class RateForm(forms.Form):
    rate = hourly_rate_field()
    effective_from = forms.DateField(
        widget=DateInput(),
        validators=[MinValueValidator(EARLIEST_DATE), MaxValueValidator(LATEST_DATE)],
        help_text="Applies to unpaid interviews on or after this date. Paid interviews keep the rate they were paid at.",
    )


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
