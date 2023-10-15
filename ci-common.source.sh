SLUG=vhs-decode-auto-audio-align


DIR_APP_EXE_RELATIVE=VhsDecodeAutoAudioAlign
DIR_APP_BUILD_RELATIVE=build
SLN_APP=VhsDecodeAutoAudioAlign.sln
BIN_APP=VhsDecodeAutoAudioAlign.exe
BIN_APP_TEST=VhsDecodeAutoAudioAlign.Test.dll
DIR_NUPKG_RELATIVE=packages

function die
{
    echo "$@"
    exit 1
}

function file_or_die
{
    if [[ ! -f "$1" ]] ; then
        die "Couldn't find file '$1' from '$(pwd)'"
    fi
}


# https://docs.gitlab.com/ee/ci/variables/predefined_variables.html

V_MAJOR=""
V_MINOR=""
V_PATCH=""
V_PRE=""

function detect_version
{
    # e.g. "v1.0.0"
    if [[ "$CI_COMMIT_TAG" == "v"* ]] ; then
        local clean=${CI_COMMIT_TAG:1}
        V_MAJOR=$(echo $clean | cut -d . -f 1)
        V_MINOR=$(echo $clean | cut -d . -f 2)
        V_PATCH=$(echo $clean | cut -d . -f 3)
        V_PRE=""
    fi

    if [[ "$V_MAJOR" == "" ]] || [[ "$V_MAJOR" == "" ]] || [[ "$V_MAJOR" == "" ]] ; then 
        V_MAJOR=0
        V_MINOR=0
        V_PATCH=0
        V_PRE="c${CI_COMMIT_SHORT_SHA}"
    fi

}

detect_version

SEMVER="${V_MAJOR}.${V_MINOR}.${V_PATCH}"

if [[ "$V_PRE" != "" ]] ; then
    SEMVER="${SEMVER}-$V_PRE"
fi


echo "Detected semver '$SEMVER'"
