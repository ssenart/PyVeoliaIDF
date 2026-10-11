"""The TLS settings: the Veolia site does not send its intermediate certificate, so the library brings it."""

import ssl
from importlib import resources

import certifi

CERTIFICATE_PACKAGE = "pyveoliaidf.certs"

# The Gandi intermediate that signs connexion.leaudiledefrance.fr, which the site leaves out of its chain.
INTERMEDIATE_CERTIFICATE = "gandi_rsa_dv_ssl_ca_3.pem"


def build_ssl_context() -> ssl.SSLContext:
    """Returns a TLS context that trusts the usual authorities (certifi) and the missing intermediate certificate."""

    context = ssl.create_default_context(cafile=certifi.where())
    certificate = resources.files(CERTIFICATE_PACKAGE).joinpath(INTERMEDIATE_CERTIFICATE).read_text(encoding="ascii")
    context.load_verify_locations(cadata=certificate)

    return context
