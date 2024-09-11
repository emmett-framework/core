from .response import HTTPRedirectResponse, HTTPStringResponse


def abort(current, code: int, body: str = ""):
    response = current.response
    response.status = code
    raise HTTPStringResponse(code, body=body, cookies=response.cookies)


def redirect(current, location: str, status_code: int = 303):
    response = current.response
    response.status = status_code
    raise HTTPRedirectResponse(status_code, location, response.cookies)
