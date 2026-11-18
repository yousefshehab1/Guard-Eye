from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from dashboard.models import Alert
from django.db.models import Count
from datetime import timedelta
from django.db.models.functions import ExtractHour
from django.utils import timezone

# خريطة ترجمة الأنواع للعربي
THREAT_TYPE_MAP = {
    'fire': 'حريق',
    'violence': 'عنف',
    'thief': 'لص',
    'thief_mask': 'لص مقنع',
    'weapon': 'سلاح',
}
# خريطة ترجمة الخطورة
SEVERITY_MAP = {
    'low': 'منخفضة',
    'medium': 'متوسطة',
    'high': 'عالية',
}

@login_required
def analytics_dashboard(request):
    """عرض صفحة لوحة التحكم التحليلية."""
    return render(request, 'dashboard/analytics_dashboard.html')

@login_required
def analytics_data(request):
    """نقطة نهاية API لجلب البيانات التحليلية."""
    # دعم جلب الأنواع فقط
    if request.GET.get('only_types') == '1':
        # Return all desired threat types for the dropdown, with their Arabic labels
        all_desired_types = []
        for val_en, label_ar in THREAT_TYPE_MAP.items():
            all_desired_types.append({'value': val_en, 'label': label_ar})
        return JsonResponse({'threat_types': all_desired_types})

    # الفلاتر
    date_range = request.GET.get('date_range', 'all')
    threat_type = request.GET.get('threat_type', 'all')
    severity = request.GET.get('severity', 'all')
    custom_date = request.GET.get('custom_date')

    print(f"[DEBUG] Received filters: date_range={date_range}, threat_type={threat_type}, severity={severity}, custom_date={custom_date}")

    end_date = timezone.now()
    if date_range == 'today':
        start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_range == 'last_week':
        # احسب بداية الأسبوع الماضي (الاثنين) ونهايته (الأحد)
        today = end_date.date()
        start_of_this_week = today - timedelta(days=today.weekday())
        start_date = start_of_this_week - timedelta(days=7)
        end_date = start_of_this_week - timedelta(seconds=1)
        start_date = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_date = timezone.make_aware(timezone.datetime.combine(end_date, timezone.datetime.max.time()))
    elif date_range == 'last_month':
        start_date = (end_date.replace(day=1) - timedelta(days=1)).replace(day=1)
        end_date = end_date.replace(day=1) - timedelta(days=1)
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif date_range == 'custom' and custom_date:
        start_date = timezone.make_aware(timezone.datetime.strptime(custom_date, '%Y-%m-%d'))
        end_date = start_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        # إذا كانت date_range هي 'all' أو غير صالحة، استخدم أول تنبيه كتاريخ بداية
        first_alert = Alert.objects.order_by('timestamp').first()
        start_date = first_alert.timestamp if first_alert else timezone.now() - timedelta(days=30)
        end_date = timezone.now()

    alerts_qs = Alert.objects.filter(timestamp__range=(start_date, end_date)).filter(user=request.user)
    print(f"[DEBUG] Alerts after date range and user filter: {alerts_qs.count()}")

    if threat_type != 'all':
        alerts_qs = alerts_qs.filter(category__iexact=threat_type)
        print(f"[DEBUG] Alerts after threat type filter ('{threat_type}'): {alerts_qs.count()}")
    if severity != 'all':
        alerts_qs = alerts_qs.filter(severity__iexact=severity)
        print(f"[DEBUG] Alerts after severity filter ('{severity}'): {alerts_qs.count()}")

    # إجمالي التنبيهات
    total_alerts = alerts_qs.count()
    # عدد كل مستوى خطورة
    high_severity_count = alerts_qs.filter(severity='high').count()
    medium_severity_count = alerts_qs.filter(severity='medium').count()
    low_severity_count = alerts_qs.filter(severity='low').count()

    # توزيع الأنواع مع الترجمة
    # Get counts for existing categories
    existing_threat_counts = alerts_qs.values('category').annotate(count=Count('category'))
    existing_threat_counts_map = {item['category']: item['count'] for item in existing_threat_counts}

    # Create a list with all desired categories, with counts (0 if no alerts)
    threat_counts = []
    for category_en, category_ar in THREAT_TYPE_MAP.items():
        threat_counts.append({
            'category': category_en, # Keep English for value
            'category_display': category_ar, # Use Arabic for display
            'count': existing_threat_counts_map.get(category_en, 0)
        })
    # Sort by count descending, then by Arabic display name ascending
    threat_counts.sort(key=lambda x: (x['count'], x['category_display']), reverse=True)

    # توزيع الخطورة مع الترجمة
    severity_distribution = alerts_qs.values('severity').annotate(count=Count('severity'))
    severity_distribution = [
        {'severity': SEVERITY_MAP.get(item['severity'], item['severity']), 'count': item['count']} for item in severity_distribution
    ]
    # التنبيهات اليومية
    daily_alerts = alerts_qs.extra({'day': "date(timestamp)"}).values('day').annotate(count=Count('id')).order_by('day')
    # التنبيهات حسب الساعة
    alerts_by_hour = alerts_qs.annotate(hour=ExtractHour('timestamp')).values('hour').annotate(count=Count('id')).order_by('hour')

    data = {
        'total_alerts': total_alerts,
        'high_severity_count': high_severity_count,
        'medium_severity_count': medium_severity_count,
        'low_severity_count': low_severity_count,
        'threat_counts': threat_counts,
        'daily_alerts': list(daily_alerts),
        'severity_distribution': severity_distribution,
        'alerts_by_hour': list(alerts_by_hour),
        'start_date': str(start_date),
        'end_date': str(end_date),
    }
    return JsonResponse(data) 