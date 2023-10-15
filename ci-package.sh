#!/bin/bash

source ci-common.source.sh

cd "$DIR_APP_BUILD_RELATIVE" || die "'$DIR_APP_BUILD_RELATIVE' does not exist"

zip_build_dir="${SLUG}_${SEMVER}"
mkdir "$zip_build_dir"

function add_file
{
    local src="$1"

    file_or_die "$src"
    cp -v "$src" "$zip_build_dir/$2"
}


add_file "$BIN_APP"
add_file "Binah.dll"
add_file "$FILE_BUILD_INFO_TXT"

add_file "../CHANGELOG.md" "CHANGELOG.md"
add_file "../LICENSE" "LICENSE-app.txt"
add_file "../$DIR_NUPKG_RELATIVE/Binah"*"/content/license"* "LICENSE-Binah.txt"

zip -r "${zip_build_dir}.zip" "$zip_build_dir"
mv  "${zip_build_dir}.zip" ../  # that's where the gitlab yaml looks for it
