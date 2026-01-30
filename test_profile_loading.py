#!/usr/bin/env python
"""Test that profile loading works correctly in main.py"""

from pyf.aggregator.profiles import ProfileManager
from pyf.aggregator.main import parser

# Test 1: Profile argument is parsed
args = parser.parse_args(["-f", "-t", "test", "-p", "plone"])
assert hasattr(args, "profile"), "profile attribute missing"
assert args.profile == "plone", f"Expected profile='plone', got {args.profile}"
print("✓ Test 1 passed: Profile argument parsed correctly")

# Test 2: ProfileManager can load the profile
pm = ProfileManager()
profile = pm.get_profile("plone")
assert profile is not None, "Profile 'plone' not found"
assert "classifiers" in profile, "Profile missing 'classifiers' key"
assert len(profile["classifiers"]) > 0, "Profile has no classifiers"
print(
    f"✓ Test 2 passed: Profile 'plone' loaded with {len(profile['classifiers'])} classifiers"
)

# Test 3: Invalid profile should be detectable
invalid_profile = pm.get_profile("nonexistent")
assert invalid_profile is None, "Invalid profile should return None"
print("✓ Test 3 passed: Invalid profile returns None")

# Test 4: List available profiles
profiles = pm.list_profiles()
assert "plone" in profiles, "'plone' not in available profiles"
assert "django" in profiles, "'django' not in available profiles"
assert "flask" in profiles, "'flask' not in available profiles"
print(f"✓ Test 4 passed: Available profiles: {', '.join(profiles)}")

print("\nAll tests passed! ✓")
