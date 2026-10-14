"""The handbook's pure rules: validating the source files, building passages and chunks, hashing
the content, and deciding who a section applies to.

Pure, like everything under app.domain: text and parsed values go in, data comes out. Reading the
files and their YAML front matter is the module's job (app.modules.handbook), because YAML is a
parsing dependency the domain must not import.
"""
