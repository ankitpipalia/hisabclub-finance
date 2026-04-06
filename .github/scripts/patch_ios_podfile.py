from pathlib import Path
import sys

podfile = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('mobile/ios/Podfile')
text = podfile.read_text()
marker = "      :ccache_enabled => ccache_enabled?(podfile_properties),\n    )\n"
injection = "      :ccache_enabled => ccache_enabled?(podfile_properties),\n    )\n\n    installer.pods_project.targets.each do |target|\n      target.build_configurations.each do |config|\n        config.build_settings['SWIFT_VERSION'] = '6.0'\n        config.build_settings['SWIFT_STRICT_CONCURRENCY'] = 'minimal'\n      end\n    end\n"
if "SWIFT_VERSION'] = '6.0'" not in text:
    if marker not in text:
        raise SystemExit(f'Expected post_install marker not found in {podfile}')
    text = text.replace(marker, injection, 1)
    podfile.write_text(text)
    print(f'Patched {podfile}')
else:
    print(f'Already patched {podfile}')
