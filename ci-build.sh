#!/bin/bash

source ci-common.source.sh

function gen_build_info_cs
{
    local cs="$1"
    
    file_or_die "$cs"
    
    echo "static class BuildInfo {" > "$cs"
    
    echo "public const string Commit = \"$CI_COMMIT_SHA\";" >> "$cs"
    echo "public const string CommitShort = \"$CI_COMMIT_SHORT_SHA\";" >> "$cs"
    echo "public const string BuildJob = \"$CI_JOB_URL\";" >> "$cs"
    echo "public const string BuildTime = \"$(date --iso-8601=seconds)\";" >> "$cs"

    echo "public const string VersionMajor = \"$V_MAJOR\";" >> "$cs"
    echo "public const string VersionMinor = \"$V_MINOR\";" >> "$cs"
    echo "public const string VersionPatch = \"$V_PATCH\";" >> "$cs"
    echo "public const string VersionSemantic = \"$SEMVER\";" >> "$cs"
    
    echo "}" >> "$cs"
    
    echo "<build-info file=\"$cs\">"
    cat "$cs"
    echo "</build-info>"
}

function build_net
{
    local _owd="$(pwd)"
    cd "$DIR_APP" || die "Couldn't cd to '$DIR_APP'"
    
    local pkg="local-pkg"
    mkdir -p $pkg
    nuget source Add -Name local -Source "$(pwd)/$pkg"
    curl -L https://gitlab.com/wolfre/binah/-/jobs/940117983/artifacts/raw/build/Binah.2.0.4.nupkg > "$pkg/Binah.2.0.4.nupkg"
    
    nuget restore "$DIR_APP_EXE_RELATIVE/packages.config" -PackagesDirectory $DIR_NUPKG_RELATIVE
    nuget restore "VhsDecodeAutoAudioAlign.Test/packages.config" -PackagesDirectory $DIR_NUPKG_RELATIVE

    file_or_die "$SLN_APP"
    gen_build_info_cs "$DIR_APP_EXE_RELATIVE/BuildInfo.cs"
    msbuild "$SLN_APP" /property:Configuration=Release
    file_or_die "$DIR_APP_BUILD_RELATIVE/$BIN_APP"
    file_or_die "$DIR_APP_BUILD_RELATIVE/$BIN_APP_TEST"

    cd "$_owd"
    echo "APP build done"
}

build_net
