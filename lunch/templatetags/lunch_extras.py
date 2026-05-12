from django import template

register = template.Library()


@register.filter
def dict_get(d, key):
    """Holt einen Wert aus einem dict per beliebigem Key (auch Tupel/Date)."""
    if d is None:
        return None
    try:
        return d.get(key)
    except AttributeError:
        return None
