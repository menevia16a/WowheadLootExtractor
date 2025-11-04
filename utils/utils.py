"""
Utility functions for string manipulation, file handling, and common operations.
"""

import re
import time


def sanitize_filename(name, maxlen=64):
    """
    Sanitize a string to be safe for filenames.
    
    Keeps alphanumerics, dashes and underscores. Collapses spaces and
    non-word characters into underscores and trims to maxlen.
    
    Args:
        name: String to sanitize
        maxlen: Maximum length of result
        
    Returns:
        Sanitized filename-safe string
    """
    if not name:
        return ''

    # normalize whitespace
    s = str(name).strip()

    # remove quotes and control chars
    s = re.sub(r'["\'"\r\n\t]+', ' ', s)

    # Replace any sequence of non-alnum with underscore
    s = re.sub(r'[^A-Za-z0-9]+', '_', s)
    s = re.sub(r'_{2,}', '_', s)
    s = s.strip('_')

    if len(s) > maxlen:
        s = s[:maxlen].rstrip('_')

    return s or str(int(time.time()))


def clean_js_string(s):
    """
    Clean a JavaScript string extracted from HTML.
    
    Strips surrounding quotes, unescapes common sequences, removes HTML tags,
    and collapses whitespace.
    
    Args:
        s: Raw JavaScript string
        
    Returns:
        Cleaned string
    """
    if not s:
        return ''

    # strip surrounding quotes if present
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1]

    # unescape some common sequences and collapse whitespace
    s = s.replace('\\n', ' ').replace('\\r', ' ').replace('\\t', ' ')
    s = s.replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')

    # strip HTML tags
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r'\s+', ' ', s).strip()

    return s


def find_matching_bracket(s, start_idx, open_ch='[', close_ch=']'):
    """
    Find the index of the closing bracket matching the opening bracket at start_idx.
    
    Handles quoted strings and escape sequences properly.
    
    Args:
        s: String to search in
        start_idx: Index of opening bracket
        open_ch: Opening bracket character (default '[')
        close_ch: Closing bracket character (default ']')
        
    Returns:
        Index of matching closing bracket, or -1 if not found
    """
    i = start_idx
    depth = 0
    in_str = None
    esc = False
    n = len(s)

    for idx in range(i, n):
        ch = s[idx]

        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == in_str:
                in_str = None
        else:
            if ch == '"' or ch == "'":
                in_str = ch
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1

                if depth == 0:
                    return idx

    return -1


def extract_objects_from_array_str(s):
    """
    Extract individual JSON-like objects from a JavaScript array string.
    
    Uses brace-matching to reliably extract top-level objects without
    requiring strict JSON parsing.
    
    Args:
        s: Array string content
        
    Returns:
        List of object strings
    """
    objs = []
    i = 0
    n = len(s)

    while i < n:
        ch = s[i]

        if ch == '{':
            start = i
            i += 1
            depth = 1
            in_str = None
            esc = False

            while i < n and depth > 0:
                c = s[i]

                if in_str:
                    if esc:
                        esc = False
                    elif c == '\\':
                        esc = True
                    elif c == in_str:
                        in_str = None
                else:
                    if c == '"' or c == "'":
                        in_str = c
                    elif c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1

                i += 1

            objs.append(s[start:i])
        else:
            i += 1

    return objs


def compute_depth_at(s, idx):
    """
    Compute bracket depth at a given index in a string.
    
    Accounts for quoted strings and escape sequences.
    
    Args:
        s: String to analyze
        idx: Index position
        
    Returns:
        Bracket depth at that position
    """
    depth = 0
    in_str = None
    esc = False
    i = 0

    while i < idx:
        ch = s[i]

        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue

        if ch == '"' or ch == "'":
            in_str = ch
            i += 1
            continue

        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1

        i += 1

    return depth
