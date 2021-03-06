"""
This module implements a fast SGML parser using xml.parsers.expat.
It quickly collects the text content under a certain XML tag in a document.
It deals with multiple documents in a single XML file.

In addition, it implements a wrapper to mini dom that eases the creation of simple 
sgml-formatted document container files.

@author: wilkeraziz
"""
import gzip
import xml.parsers.expat
import re
from xml.dom.minidom import getDOMImplementation
from xml.sax.saxutils import escape, unescape
from functools import partial
from discourse import command


class TextFromSGML(object):

    def __init__(self, content, text_under, root=None):
        """
        Parses the XML content of a file.
        :param str content: XML content
        :param str text_under: tag name under which we will find text (e.g. doc, text)
        :param str root: if not None, it is interpreted as the single root tag name to be added to the XML content
        """
        assert text_under is not None, 'You need to specify a text tag'
        parser = xml.parsers.expat.ParserCreate()
        # parser state
        state = {}
        # parsed documents
        state['documents'] = []
        # temporary data (e.g. curent document's id, sentences and status)
        state['_attrs'] = None
        state['_doc'] = None
        state['_reading'] = False
        state['_text_under'] = text_under
        # handlers
        parser.StartElementHandler = partial(TextFromSGML._start_element, state=state)
        parser.EndElementHandler = partial(TextFromSGML._end_element, state=state)
        parser.CharacterDataHandler = partial(TextFromSGML._char_data, state=state)
        # add root if necessary
        if root is None:
            parser.Parse(content, 1)
        else:
            parser.Parse('<{0}>{1}</{0}>'.format(root, content), 1)
        # store parser's state
        self._state = state

    def iterdocs(self):
        """Iterates over documents in a given sgm file -> content, attributes"""
        for content, attrs in self._state['documents']:
            yield content, attrs

    @staticmethod
    def _start_element(name, attrs, state):
        """starts a document"""
        if name.lower() == 'doc':
            state['_doc'] = []
            state['_attrs'] = dict(attrs)
        if state['_text_under'].lower() == name.lower():
            state['_reading'] = True

    @staticmethod
    def _end_element(name, state):
        """ends a document"""
        if name.lower() == 'doc':
            state['documents'].append((state['_doc'], state['_attrs']))
            state['_doc'] = None
            state['_attrs'] = None
        if state['_text_under'].lower() == name.lower():
            state['_reading'] = False

    @staticmethod
    def _char_data(txt_data, state):
        """stores non blank lines in a document"""
        if state['_reading']:
            # encode utf-8 into a python string
            line = txt_data.encode('utf-8').strip()
            if line:
                state['_doc'].append(line)


class MakeSGMLDocs(object):

    def __init__(self, **kwargs):
        self._dom = getDOMImplementation()
        self._docs = self._dom.createDocument(None, 'docs', None)
        for k, v in kwargs.iteritems():
            self._docs.documentElement.setAttribute(k, v)

    def add(self, doc_text, **kwargs):
        """adds a document (as a string)"""
        doc = self._docs.createElement('doc')
        for k, v in kwargs.iteritems():
            doc.setAttribute(k, v)
        # decode python strings into utf-8
        doc.appendChild(self._docs.createTextNode(doc_text.decode('utf-8')))
        self._docs.documentElement.appendChild(doc)
    
    def add_doc(self, segments, **kwargs):
        """adds a document as a list of segments"""
        doc = self._docs.createElement('doc')
        for k, v in kwargs.iteritems():
            doc.setAttribute(k, v)
        # decode python strings into utf-8
        for i, txt_seg in enumerate(segments):
            seg = self._docs.createElement('seg')
            seg.setAttribute('id', str(i))
            seg.appendChild(self._docs.createTextNode(txt_seg.decode('utf-8')))
            doc.appendChild(seg)
        self._docs.documentElement.appendChild(doc)

    def writegz(self, path):
        if not path.endswith('.gz'):
            path += '.gz'
        with gzip.open(path, 'wb') as fout:
            # returns utf-8 encoded into python string
            fout.write(self._docs.toprettyxml(encoding='utf-8'))
    
    def write(self, ostream):
        # returns utf-8 encoded into python string
        ostream.write(self._docs.toprettyxml(encoding='utf-8'))


def wmtbadsgml_iterdoc(istream, empty=''):
    """
    Parses WMT's baddly formatted SGML files.
    They are not really XML files, they are simply plain text with XML-style tags.
    If you parse them using an XML parser, you will have problems with invalid chars all over.

    Arguments
    ---------
    istream: an iterable returning the lines in the file
    empty: what to output if a segment is empty

    Returns
    -------
    a generator of tuples of the kind (content, attributes) where each tuple represents a document
    the content is a list of segments
    the attributes is a dictionary of string keys and string values
    
    >>> docs = list(wmtbadsgml_iterdoc(_WMT_SGML_EXAMPLE_))
    >>> len(docs)
    3
    >>> content, attrs = docs[0]
    >>> content
    ['A Republican strategy to counter the re-election of Obama', 'Republican leaders justified their policy by the need to combat electoral fraud.', 'Indeed, Republican lawyers identified only 300 cases of electoral fraud in the United States in a decade.']
    >>> sorted(attrs.iteritems(), key=lambda (k,v): k)
    [('docid', 'cyberpresse/2012/12/01/1564248'), ('genre', 'news'), ('origlang', 'fr'), ('sysid', 'ref')]
    >>> content, attrs = docs[1]
    >>> content  # note the EMPTY segment at the end of the list
    ['One thing is certain: these new provisions will have a negative impact on voter turn-out.', '']
    >>> content, attrs = docs[2]
    >>> content  # note how this one also recovered the segments even though they were not inline
    ['One thing is certain: these new provisions will have a negative impact on voter turn-out.', 'Republican leaders justified their policy by the need to combat electoral fraud.', 'Indeed, Republican lawyers identified only 300 cases of electoral fraud in the United States in a decade.']
    >>> docs = list(wmtbadsgml_iterdoc(_WMT_SGML_EXAMPLE_, empty='<EMPTY>'))  # use it like this if you don't like empty strings
    >>> docs[1][0]
    ['One thing is certain: these new provisions will have a negative impact on voter turn-out.', '<EMPTY>']
    """

    # matching tags of regardless of case
    start_doc_re = re.compile('<doc(.*)>', re.IGNORECASE)
    end_doc_re = re.compile('</doc>', re.IGNORECASE)
    attr_re = re.compile('([^= ]+)="([^"]+)"')
    seg_re = re.compile('<seg[^>]*>(.*)</seg>', re.IGNORECASE)
    start_seg_re = re.compile('<seg[^>]*>(.*)', re.IGNORECASE)
    end_seg_re = re.compile('(.*)</seg>', re.IGNORECASE)

    content = None
    attrs = None

    iterable = iter(istream)

    for line in iterable: 
        # end doc
        m = end_doc_re.search(line)
        if m is not None:
            yield content, attrs
            content = None
            attrs = None
            continue

        # begin doc
        m = start_doc_re.search(line)
        if m is not None:
            content = []
            attrs = dict(attr_re.findall(m.group(1)))
            continue
        
        # inline segments
        m = seg_re.search(line)
        if m is not None:
            seg_str = m.group(1).strip()
            content.append(seg_str if seg_str else empty)
            continue

        # multiple line segments
        m = start_seg_re.search(line)
        if m is not None:
            parts = [m.group(1).strip()]
            for more in iterable:
                m = end_seg_re.search(more)
                if m is not None:
                    parts.append(m.group(1).strip())
                    break
                else:
                    parts.append(more.strip())
            content.append(' '.join(parts).strip())


def badsgml_iterdoc(istream, empty=''):
    """
    """

    # matching tags of regardless of case
    start_doc_re = re.compile('<doc(.*)>', re.IGNORECASE)
    end_doc_re = re.compile('</doc>', re.IGNORECASE)
    attr_re = re.compile('([^= ]+)="([^"]+)"')

    content = None
    attrs = None

    for line in istream: 
        # end doc
        m = end_doc_re.search(line)
        if m is not None:
            yield content, attrs
            content = None
            attrs = None
            continue

        # begin doc
        m = start_doc_re.search(line)
        if m is not None:
            content = []
            attrs = dict(attr_re.findall(m.group(1)))
            continue
        
        # content
        if content is not None:
            line = line.strip()
            content.append(line if line else empty)


def main(args):
    """
    Converts doctext to good SGML
    Arguments
    ---------
    argparse's args
    """
    from discourse.doctext import iterdoctext
    from discourse.docsgml import MakeSGMLDocs
    import sys

    sgmler = MakeSGMLDocs()
    [sgmler.add_doc(content, **attrs) for content, attrs in iterdoctext(args.input)]
    sgmler.write(args.output)


@command('docsgml', 'preprocessing')
def argparser(parser=None, func=main):
    """
    Configures and returns a parser for the tool 'docsgml'.

    Arguments
    ---------
    parser: a clean argparse parser to be configured (the program name won't be changed),
        or None in which case a parser will be created
    main: the main function to be called when the program is invoked

    Returns
    -------
    a configured parser
    """
    import sys
    import argparse

    if parser is None:
        parser = argparse.ArgumentParser(prog='docsgml')

    parser.description = "Convert from doctext to properly formatted SGML"

    parser.add_argument('input', nargs='?', 
            type=argparse.FileType('r'), default=sys.stdin,
            help='a WMT file')
    
    parser.add_argument('output', nargs='?', 
            type=argparse.FileType('w'), default=sys.stdout,
            help='an SGML file')
    
    if func is not None:
        parser.set_defaults(func=func)

    return parser


def fixwmt_main(args):
    """
    Recover from WMT's bad SGML markup producing doctext by default (or good SGML)
    Arguments
    ---------
    argparse's args
    """

    from doctext import writedoctext
    from discourse.docsgml import MakeSGMLDocs
    
    if args.sgml:
        sgmler = MakeSGMLDocs()

    for did, (content, attrs) in enumerate(wmtbadsgml_iterdoc(args.input, '<EMPTY>')):
        if args.add_id:
            attrs['docid'] = did
        for kv in args.attr:
            k, v = kv.split('=')
            attrs[k] = v
        
        if args.sgml:
            sgmler.add_doc(content, **attrs)
        else:
            writedoctext(args.output, content, **attrs)

    if args.sgml:
        sgmler.write(args.output)


@command('fixwmt', 'preprocessing')
def fixwmt_argparser(parser=None, func=fixwmt_main):
    """
    Configures and returns a parser for the tool 'fixwmt'.

    Arguments
    ---------
    parser: a clean argparse parser to be configured (the program name won't be changed),
        or None in which case a parser will be created
    main: the main function to be called when the program is invoked

    Returns
    -------
    a configured parser
    """
    import argparse
    import sys


    if parser is None:
        parser = argparse.ArgumentParser(prog='fixwmt')
    
    parser.description = "Recover from WMT's bad SGML markup"

    parser.add_argument('input', nargs='?', 
            type=argparse.FileType('r'), default=sys.stdin,
            help='WMT file')
    parser.add_argument('output', nargs='?', 
            type=argparse.FileType('w'), default=sys.stdout,
            help='doctext file (or see --sgml)')
    parser.add_argument('--add-id', 
            action='store_true',
            help='add sequential ids to the documents')
    parser.add_argument('--attr', 
            action='append',
            default=[],
            help='add a key value pair attribute to all documents (key=value)')
    parser.add_argument('--sgml', 
            action='store_true',
            help='by default we output doctext, use this flag if you prefer (proper) SGML')

    if func is not None:
        parser.set_defaults(func=func)

    return parser


if __name__ == '__main__':
    main(argparser().parse_args())


_WMT_SGML_EXAMPLE_ =  \
"""
<refset trglang="en" setid="newstest2013" srclang="any">
<doc sysid="ref" docid="cyberpresse/2012/12/01/1564248" genre="news" origlang="fr">
<h1>
<seg id="1">A Republican strategy to counter the re-election of Obama </seg>
</h1>
<p>
<seg id="2">Republican leaders justified their policy by the need to combat electoral fraud.</seg>
<seg id="4">Indeed, Republican lawyers identified only 300 cases of electoral fraud in the United States in a decade.</seg>
</p>
</doc>
<DOC sysid="ref" docid="cyberpresse/2012/12/01/1564249" genre="news" origlang="fr">
<p>
<seg id="5">One thing is certain: these new provisions will have a negative impact on voter turn-out.</seg>
<seg></seg>
</p>
</DOC>
<DOC sysid="ref" docid="cyberpresse/2012/12/01/1564249" genre="news" origlang="fr">
<p>
<seg id="5">
One thing is certain: these new provisions will have a negative impact on voter turn-out.
</seg>
<seg id="2">

Republican leaders justified their policy by the need to combat electoral fraud.</seg>
<seg id="4">Indeed, Republican lawyers identified only 300 cases of electoral fraud in the United States in a 
decade.</seg>
</p>
</DOC>
</refset>
""".split('\n')
