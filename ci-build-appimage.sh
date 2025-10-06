#!/bin/bash

source ci-common.source.sh

if [[ "$CI_JOB_TOKEN" == "" ]] ; then 
    die "CI_JOB_TOKEN was not set"
fi


export DEBIAN_FRONTEND=noninteractive

MONO_VERSION=6.12.0.199
# https://askubuntu.com/questions/596318/what-is-the-difference-between-machine-processor-and-hardware-platform
PLATFORM=$(uname -m)
MONO_ARCHIVE_NAME=mono-${MONO_VERSION}-${PLATFORM}.tar.xz
MONO_BUILD_LOG="$(pwd)/mono-build.log"

function install_basics
{
    # We assume to be running in a debian / ubuntu container ...
    echo "Installing basic packages"  
    apt update &>> "$MONO_BUILD_LOG"
    apt install -y curl ca-certificates xz-utils zip file fuse  &>> "$MONO_BUILD_LOG" || die "apt install failed"
}

function install_mono_build_deps
{
    # We assume to be running in a debian / ubuntu container ...
    echo "Installing mono build dependencies"    
    apt update &>> "$MONO_BUILD_LOG"
    apt install -y build-essential tzdata python3 cmake  &>> "$MONO_BUILD_LOG" || die "apt install failed"
}

function build_mono
{
    local ws_root="$(pwd)"
    echo "Will build mono to $ws_root/$MONO_ARCHIVE_NAME using $(nproc) cpu threads"

    local build_dir=/opt/mono
    mkdir -p $build_dir || die "couldn't create build target dir"

    mkdir -p /tmp
    cd /tmp || die "could not use tmp?!"

    install_mono_build_deps
    
    echo "Getting source ..."
    curl --output mono-src.tar.xz https://download.mono-project.com/sources/mono/mono-${MONO_VERSION}.tar.xz &>> "$MONO_BUILD_LOG"
    tar xvf mono-src.tar.xz &>> "$MONO_BUILD_LOG" || die "un-tar failed"
    ls -lah
    cd mono-${MONO_VERSION} || die "mono tar structure not as expected"

    echo "Running configure ..."
    ./configure --prefix="$build_dir" &>> "$MONO_BUILD_LOG" || die "configure failed"

    # https://serverfault.com/questions/691659/count-number-of-allowed-cpus-in-a-docker-container
    echo "Running make ..."
    make -j$(nproc) &>> "$MONO_BUILD_LOG" || die "make failed" 

    echo "Running make install ..."
    make install &>> "$MONO_BUILD_LOG" || die "make install failed" 

    echo "Checking build ..."
    "$build_dir/bin/mono" --version || die "mono could not run"

    echo "Build looks good, will package $build_dir ..."
    cd "$build_dir"
    tar c . | xz -9 -T $(nproc) --memlimit-compress=70% > "$ws_root/$MONO_ARCHIVE_NAME" || die "tar / xz failed to pack"
    
    echo "Build done!"
    cd "$ws_root"
    ls -lah
}

function build_mono_cached
{
    # This function will attempt to get a pre-built mono version from a cache, and if not available, build and cache it.
    # Building mono takes quite some time (around 45 min on a gitlab.com shared runner in 2025), so caching helps a lot.
    # The gitlab project package registry is used as cache, and the version and platform is included in the path/name,
    # to support building for more than one CPU architecture.

    function get_cache_url
    {
        local gitlab_project_id=$1
        # https://docs.gitlab.com/user/packages/generic_packages/?tab=CI%2FCD+job+token#download-a-single-file
        local base_url="${CI_API_V4_URL}/projects/${gitlab_project_id}/packages/generic"
        local pkg_url="$base_url/mono-bin/$MONO_VERSION/$MONO_ARCHIVE_NAME"
        echo -n "$pkg_url"
    }

    function pkg_looks_ok
    {
        test -f $MONO_ARCHIVE_NAME && test $(stat -c %s $MONO_ARCHIVE_NAME) -gt $(( 1024 * 1024 ))
    }

    # First we'll check for a cached pkg in our own registry ...
    curl \
        --location \
        --header "JOB-TOKEN: ${CI_JOB_TOKEN}" \
        --output $MONO_ARCHIVE_NAME \
        $(get_cache_url $CI_PROJECT_ID)

    if [[ "$?" == "0" ]] && pkg_looks_ok ; then
        echo "Got $MONO_ARCHIVE_NAME from project cache" | tee -a "$MONO_BUILD_LOG"
        return 0
    fi

    rm -f "$MONO_ARCHIVE_NAME" # just in case something was downloaded

    # If our own registry does not have the pre-build mono, we'll check the registry of the original project at 
    # https://gitlab.com/wolfre/vhs-decode-auto-audio-align just in case we are building a fork of sorts
    curl \
        --location \
        --output $MONO_ARCHIVE_NAME \
        $(get_cache_url 51120976)

    if [[ "$?" == "0" ]] && pkg_looks_ok ; then
        echo "Got $MONO_ARCHIVE_NAME from original project cache" | tee -a "$MONO_BUILD_LOG"
        return 0
    fi

    rm -f "$MONO_ARCHIVE_NAME" # just in case something was downloaded
    echo "Will need to build mono $MONO_ARCHIVE_NAME (be patient this will take quite some time) ..." | tee -a "$MONO_BUILD_LOG"

    build_mono
    if ! pkg_looks_ok ; then
        die "Build failed?!"
    fi

    echo "Build done, will upload/cache result ..."
    curl \
        --location \
        --header "JOB-TOKEN: ${CI_JOB_TOKEN}" \
        --upload-file $MONO_ARCHIVE_NAME \
        $(get_cache_url $CI_PROJECT_ID) || die "Upload failed"
}


function build_app_image
{
    local app_name=vhs-decode-aaa
    local appimage_taget="$(pwd)/${app_name}-${SEMVER}-${PLATFORM}.AppImage"
    local mono_ark="$(pwd)/$MONO_ARCHIVE_NAME"
    file_or_die "$mono_ark"

    local dist_zip_dir="${SLUG}_${SEMVER}"
    local dist_zip="$(pwd)/${dist_zip_dir}.zip"
    file_or_die "$dist_zip"

    local dir_appimage="$(pwd)/appimage"
    if [[ ! -d "$dir_appimage" ]] ; then 
        die "could not find $dir_appimage"
    fi

    local appimagetool="/tmp/appimagetool"
    curl \
        --output "$appimagetool" \
        -L \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${PLATFORM}.AppImage || die "Could not get appimagetool"
        
    chmod a+x "$appimagetool"
    "$appimagetool" --version | grep -q -i "continuous" || die "appimagetool does not seem to work"

    local dir_base=/tmp/$app_name
    
    # as per https://github.com/AppImage/AppImageKit/wiki/AppDir
    mkdir -p \
        "$dir_base/usr" \
        "$dir_base/lib" \
        "$dir_base/share/applications" \
        "$dir_base/share/icons/hicolor/256x256"

    cp -v "$dir_appimage/AppRun" "$dir_base/AppRun" || dir "copy failed"
    cp -v "$dir_appimage/vhs-decode-aaa.desktop" "$dir_base/${app_name}.desktop" || dir "copy failed"
    cp -v "$dir_appimage/vhs-decode-aaa.desktop" "$dir_base/share/applications/${app_name}.desktop" || dir "copy failed"
    cp -v "$dir_appimage/vhs-decode-aaa-256.png" "$dir_base/${app_name}.png" || dir "copy failed"
    cp -v "$dir_appimage/vhs-decode-aaa-256.png" "$dir_base/share/icons/hicolor/256x256/${app_name}.png" || dir "copy failed"    

    cd "$dir_base/usr"
    tar xf "$mono_ark" . || die "Unpack mono failed"
    "$dir_base/usr/bin/mono" --version || die "Mono not at the right spot?!"

    unzip "$dist_zip" || die "App unzip failed"
    mv "$dist_zip_dir" aaa || die "Zip structure not as expected"

    "$appimagetool" "$dir_base" "$appimage_taget" || die "Pack appimage failed"
    
    # just some final sanity smoke test
    "$appimage_taget" show-build-info  2>&1 | grep -q -i audio || die "Couldn't run appimage?!"
}


install_basics
build_mono_cached
build_app_image
