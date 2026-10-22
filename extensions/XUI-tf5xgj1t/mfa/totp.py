import datetime
import time
import base64
import hashlib
import hmac

from . import utils


class OTP(object):
    def __init__(self, s, digits=6, digest=hashlib.sha1):
        """
        @param [String] secret in the form of base32
        @option options digits [Integer] (6)
            Number of integers in the OTP
            Google Authenticate only supports 6 currently
        @option options digest [Callable] (hashlib.sha1)
            Digest used in the HMAC
            Google Authenticate only supports 'sha1' currently
        @returns [OTP] OTP instantiation
        """
        self.digits = digits
        self.digest = digest
        self.secret = s

    def generate_otp(self, input):
        """
        @param [Integer] input the number used seed the HMAC
        Usually either the counter, or the computed integer
        based on the Unix timestamp
        """
        hmac_hash = hmac.new(
            self.byte_secret(),
            self.int_to_bytestring(input),
            self.digest,
        ).digest()

        hmac_hash = bytearray(hmac_hash)
        offset = hmac_hash[-1] & 0xF
        code = (
            (hmac_hash[offset] & 0x7F) << 24
            | (hmac_hash[offset + 1] & 0xFF) << 16
            | (hmac_hash[offset + 2] & 0xFF) << 8
            | (hmac_hash[offset + 3] & 0xFF)
        )
        str_code = str(code % 10**self.digits)
        while len(str_code) < self.digits:
            str_code = "0" + str_code

        return str_code

    def byte_secret(self):
        missing_padding = len(self.secret) % 8
        if missing_padding != 0:
            self.secret += "=" * (8 - missing_padding)
        return base64.b32decode(self.secret, casefold=True)

    @staticmethod
    def int_to_bytestring(i, padding=8):
        """
        Turns an integer to the OATH specified
        bytestring, which is fed to the HMAC
        along with the secret
        """
        result = bytearray()
        while i != 0:
            result.append(i & 0xFF)
            i >>= 8
        # It's necessary to convert the final result from bytearray to bytes because
        # the hmac functions in python 2.6 and 3.3 don't work with bytearray
        return bytes(bytearray(reversed(result)).rjust(padding, b"\0"))


class TOTP(OTP):
    def __init__(self, *args, **kwargs):
        """
        @option options [Integer] interval (30) the time interval in seconds
            for OTP This defaults to 30 which is standard.
        """
        self.interval = kwargs.pop("interval", 30)
        super(TOTP, self).__init__(*args, **kwargs)

    def at(self, for_time, counter_offset=0):
        """
        Accepts either a Unix timestamp integer or a Time object.
        Time objects will be adjusted to UTC automatically
        @param [Time/Integer] time the time to generate an OTP for
        @param [Integer] counter_offset an amount of ticks to add to the time counter
        """
        if not isinstance(for_time, datetime.datetime):
            for_time = datetime.datetime.fromtimestamp(int(for_time))
        return self.generate_otp(self.timecode(for_time) + counter_offset)

    def now(self):
        """
        Generate the current time OTP
        @return [Integer] the OTP as an integer
        """
        return self.generate_otp(self.timecode(datetime.datetime.now()))

    def verify(self, otp, for_time=None, valid_window=0):
        """
        Verifies the OTP passed in against the current time OTP
        @param [String/Integer] otp the OTP to check against
        @param [Integer] valid_window extends the validity to this many counter ticks before and after the current one
        """
        if for_time is None:
            for_time = datetime.datetime.now()

        if valid_window:
            for i in range(-valid_window, valid_window + 1):
                if utils.strings_equal(str(otp), str(self.at(for_time, i))):
                    return True
            return False

        return utils.strings_equal(str(otp), str(self.at(for_time)))

    def provisioning_uri(self, name, issuer_name=None):
        """
        Returns the provisioning URI for the OTP
        This can then be encoded in a QR Code and used
        to provision the Google Authenticator app
        @param [String] name of the account
        @return [String] provisioning uri
        """
        return utils.build_uri(self.secret, name, issuer_name=issuer_name)

    def timecode(self, for_time):
        i = time.mktime(for_time.timetuple())
        return int(i / self.interval)
