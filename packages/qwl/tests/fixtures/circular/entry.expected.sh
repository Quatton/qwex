# C1 basic task
# Hash: 0xc18572bc4ff5b9fe
task:B:c1() {
  echo "c1: origin=from-B"
}
# D1 from inline module D
# Hash: 0xb4179cf0c4837d29
task:B:D:d1() {
  echo "d1: origin=from-D"
}
# C2 uses D's d1
# Hash: 0x6b6b4e4a0475f0cc
task:B:c2() {
  echo "c2 calling d1"
task:B:D:d1
}
# Original a1 from A
# Hash: 0x6b35e2001eac5e59
task:a1() {
  echo "a1: origin=from-entry"
}
# Main entry task
# Hash: 0xad313f82b5b1af3d
task:main() {
  echo "=== Testing complex inheritance ==="
# Call a1 (inherited from A) - should use entry's vars
task:a1
# Call B's c1 through submodule chain
task:B:c1
# Call B's c2 (which references D's d1)
task:B:c2
}
# Test task deduplication - reference same task twice
# Hash: 0x9646a1ee13d9f7b1
task:testDedup() {
  # Both reference a1, but a1 should only appear once in deps
task:a1
echo "between calls"
task:a1
}
# Test inline doesn't create duplicate deps
# Hash: 0x7dcffc3a2635bac
task:testInlineDedup() {
  # Inline a1 twice - no deps created
echo "a1: origin=from-entry"
echo "a1: origin=from-entry"
}
