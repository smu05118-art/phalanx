#!/usr/bin/env python3
"""Read-only validation of reviewed source, manifest, and declared shard."""
import sys
sys.dont_write_bytecode = True
from build_nebius_relationships import main

if __name__ == '__main__':
    sys.exit(main([*sys.argv[1:], '--check']))
