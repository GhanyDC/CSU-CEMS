# Static Image Assets

Place the CEMS logo file here:

    static/img/logo.png

## Logo requirements

- **File name:** `logo.png`
- **Location:** `static/img/logo.png` (this folder)
- **Recommended size:** 200×200 px minimum, square aspect ratio
- **Format:** PNG with transparent background works best
- **Usage:** Displayed in the student navigation bar (34×34 px) and on the student login page (80×80 px)

## After uploading

Run:

    python manage.py collectstatic

to copy the image to the static files serving location.

## Fallback behaviour

If `logo.png` is missing the system automatically falls back to showing the "E" letter icon so the site continues to work without the image.
