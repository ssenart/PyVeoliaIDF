"""The errors of pyveoliaidf. Every one of them is a PyVeoliaIDFError."""


# ------------------------------------------------------------------------------------------------------------
class PyVeoliaIDFError(Exception):
    """The base of the errors that pyveoliaidf raises on its own."""


# ------------------------------------------------------------------------------------------------------------
class ServerError(PyVeoliaIDFError):
    """The Veolia site answered with an error, or did not answer."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


# ------------------------------------------------------------------------------------------------------------
class RateLimitError(ServerError):
    """The site refused the calls sent back to back (HTTP 429), and kept refusing them after the retries."""

    def __init__(self, message: str):
        super().__init__(message, 429)


# ------------------------------------------------------------------------------------------------------------
class LoginError(ServerError):
    """The site refused the login: the credentials are wrong, or the login page changed."""


# ------------------------------------------------------------------------------------------------------------
class SessionExpiredError(ServerError):
    """The site no longer accepts the session: it has expired, or it has been closed on the server."""


# ------------------------------------------------------------------------------------------------------------
class UnexpectedResponseError(ServerError):
    """The site answered, but not in the shape the library knows: the site has probably changed.

    The message names what is missing or malformed, never the content of the answer, which may hold secrets.
    """


# ------------------------------------------------------------------------------------------------------------
class NotLoggedInError(PyVeoliaIDFError, ConnectionError):
    """A call needs a session: the client has not logged in, or has logged out."""


# ------------------------------------------------------------------------------------------------------------
class UnknownMeterError(PyVeoliaIDFError, LookupError):
    """The meter number is not one of the meters of the contract."""

    def __init__(self, meter_number: str):
        super().__init__(f"The meter {meter_number} does not exist in this contract.")
        self.meter_number = meter_number


# ------------------------------------------------------------------------------------------------------------
class UnknownContractError(PyVeoliaIDFError, LookupError):
    """The contract number is not one of the contracts of the account."""

    def __init__(self, contract_number: str):
        super().__init__(f"The contract {contract_number} does not exist in this account.")
        self.contract_number = contract_number
