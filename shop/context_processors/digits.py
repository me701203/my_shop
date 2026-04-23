def digit_mode(request):
    return {"DIGIT_MODE": request.session.get("digits", "en")}
