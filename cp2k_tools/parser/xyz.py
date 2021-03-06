
import re
import contextlib


try:
    # PY2, bytes are also strings and need to be imbued
    STRING_TYPES = (unicode, )
except:
    STRING_TYPES = (str, )


@contextlib.contextmanager
def as_byteorstringlike(fh_or_content):
    """
    Yields a tuple (content, content_type),
    where content_type is True if content is a unicode string and does not need imbueing,
    and False if it is a byte-like and needs to be encoded.
    """

    if isinstance(fh_or_content, STRING_TYPES):
        yield fh_or_content, True
    elif isinstance(fh_or_content, bytes):
        yield fh_or_content, False
    else:
        # if the handle is a file handle, use mmap to return a bitelike object
        import mmap
        mmapped = mmap.mmap(fh_or_content.fileno(), 0, access=mmap.ACCESS_READ)

        try:
            yield mmapped, False
        finally:
            mmapped.close()


# MULTILINE and VERBOSE regex to match coordinate lines in a frame:
POS_MATCH_REGEX = r"""
^                                                                             # Linestart
[ \t]*                                                                        # Optional white space
(?P<sym>[A-Za-z]+[A-Za-z0-9]*)\s+                                             # get the symbol
(?P<x> [\-|\+]?  ( \d*[\.]\d+  | \d+[\.]?\d* )  ([E | e][+|-]?\d+)? ) [ \t]+  # Get x
(?P<y> [\-|\+]?  ( \d*[\.]\d+  | \d+[\.]?\d* )  ([E | e][+|-]?\d+)? ) [ \t]+  # Get y
(?P<z> [\-|\+]?  ( \d*[\.]\d+  | \d+[\.]?\d* )  ([E | e][+|-]?\d+)? )         # Get z
"""

# MULTILINE and VERBOSE regex to match frames:
FRAME_MATCH_REGEX = r"""
                                                            # First line contains an integer
                                                            # and only an integer: the number of atoms
^[ \t]* (?P<natoms> [0-9]+) [ \t]*[\n]                      # End first line
(?P<comment>.*) [\n]                                        # The second line is a comment
(?P<positions>                                              # This is the block of positions
    (
        (
            \s*                                             # White space in front of the element spec is ok
            (
                [A-Za-z]+[A-Za-z0-9]*                       # Element spec
                (
                   \s+                                      # White space in front of the number
                   [\- | \+ ]?                              # Plus or minus in front of the number (optional)
                    (\d*                                    # optional decimal in the beginning .0001 is ok, for example
                    [\.]                                    # There has to be a dot followed by
                    \d+)                                    # at least one decimal
                    |                                       # OR
                    (\d+                                    # at least one decimal, followed by
                    [\.]?                                   # an optional dot
                    \d*)                                    # followed by optional decimals
                    ([E | e][+|-]?\d+)?                     # optional exponents E+03, e-05
                ){3}                                        # I expect three float values
                |
                \#                                          # If a line is commented out, that is also ok
            )
            .*                                              # I do not care what is after the comment or the position spec
            |                                               # OR
            \s*                                             # A line only containing white space
         )
        [\n]                                                # line break at the end
    )+
)                                                           # A positions block should be one or more lines
"""


class XYZParser:
    @staticmethod
    def parse_iter(fh_or_string):
        """Generates nested tuples for frames in XYZ files.

        Args:
            string: a string containing XYZ-structured text

        Yields:
            tuple: `(natoms, comment, atomiter)` for each frame
            in the XYZ data where `atomiter` is an iterator yielding a
            nested tuple `(symbol, (x, y, z))` for each entry.

        Raises:
            TypeError: If the number of atoms specified for the frame does not match
                the number of atom entries in the file.

        Examples:
            >>> print(len(list(XYZParser.parse_iter('''
            ... 5
            ... no comment
            ...  C         5.0000000000        5.0000000000        5.0000000000
            ...  H         5.6401052216        5.6401052216        5.6401052216
            ...  H         4.3598947806        4.3598947806        5.6401052208
            ...  H         4.3598947806        5.6401052208        4.3598947806
            ...  H         5.6401052208        4.3598947806        4.3598947806
            ... 5
            ... no comment
            ...  C         5.0000000000        5.0000000000        5.0000000000
            ...  H         5.6401902064        5.6401902064        5.6401902064
            ...  H         4.3598097942        4.3598097942        5.6401902063
            ...  H         4.3598097942        5.6401902063        4.3598097942
            ...  H         5.6401902063        4.3598097942        4.3598097942
            ... 5
            ... no comment
            ...  C         5.0000000000        5.0000000000        5.0000000000
            ...  H         5.6401902064        5.6401902064        5.6401902064
            ...  H         4.3598097942        4.3598097942        5.6401902063
            ...  H         4.3598097942        5.6401902063        4.3598097942
            ...  H         5.6401902063        4.3598097942        4.3598097942
            ... '''))))
            3
        """

        class BlockIterator(object):
            """
            An iterator for wrapping the iterator returned by `match.finditer`
            to extract the required fields directly from the match object
            """
            def __init__(self, it, natoms):
                self._it = it
                self._natoms = natoms
                self._catom = 0

            def __iter__(self):
                return self

            def __next__(self):
                try:
                    match = next(self._it)
                except StopIteration:
                    # if we reached the number of atoms declared, everything is well
                    # and we re-raise the StopIteration exception
                    if self._catom == self._natoms:
                        raise
                    else:
                        # otherwise we got too less entries
                        raise TypeError("Number of atom entries ({}) is smaller "
                                        "than the number of atoms ({})".format(
                                            self._catom, self._natoms))

                self._catom += 1

                if self._catom > self._natoms:
                    raise TypeError("Number of atom entries ({}) is larger "
                                    "than the number of atoms ({})".format(
                                        self._catom, self._natoms))

                return (
                    match.group('sym'),
                    (
                        float(match.group('x')),
                        float(match.group('y')),
                        float(match.group('z'))
                        ))

            def next(self):
                """
                The iterator method expected by python 2.x,
                implemented as python 3.x style method.
                """
                return self.__next__()


        with as_byteorstringlike(fh_or_string) as (content, is_string):
            if is_string:
                frame_match = re.compile(FRAME_MATCH_REGEX, re.MULTILINE | re.VERBOSE)
                pos_match = re.compile(POS_MATCH_REGEX, re.MULTILINE | re.VERBOSE)
            else:
                # TODO: at this point we might have to care about the encoding of the content as well
                frame_match = re.compile(FRAME_MATCH_REGEX.encode('utf8'), re.MULTILINE | re.VERBOSE)
                pos_match = re.compile(POS_MATCH_REGEX.encode('utf8'), re.MULTILINE | re.VERBOSE)

            for block in frame_match.finditer(content):
                natoms = int(block.group('natoms'))
                yield (
                    natoms,
                    block.group('comment') if is_string else block.group('comment').decode('utf8'),
                    BlockIterator(
                        pos_match.finditer(block.group('positions')),
                        natoms)
                    )

    @staticmethod
    def parse(fh_or_string):
        """
        The same as parse_iter(...) but instead of iterators, a list of nested dicts containing again
        a list for the 'atoms' key instead of another iterator are returned.
        """
        return [{'natoms': natoms,
                 'comment': comment,
                 'atoms': list(atomiter)} for (natoms, comment, atomiter) in XYZParser.parse_iter(fh_or_string)]
