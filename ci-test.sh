#!/bin/bash

source ci-common.source.sh

function test_app
{
    local runner_rel="$(find -iname "nunit3-console.exe" | head -n 1)"
    local runner="$(realpath "$runner_rel")"
    
    file_or_die "$runner"
    echo "Found runner: '$runner'"
    
    cd "$DIR_APP_BUILD_RELATIVE" || die "Build output not at '$DIR_APP_BUILD_RELATIVE'"
    
    local xslt_url="https://raw.githubusercontent.com/nunit/nunit-transforms/master/nunit3-junit/nunit3-junit.xslt"
    local xslt=nunit3-junit.xslt
    echo "About to get the XSLT to transform NUnit3 -> JUnit results ..."
    curl "$xslt_url" > $xslt
    md5sum $xslt
    cat $xslt | grep -q "xsl:stylesheet version=" || die "'$xslt' does not seem useable"

    local junit=nunit-results.junit.xml
    mono --debug "$runner" "$BIN_APP_TEST" --labels=Before "--result=nunit-results.nunit3.xml;format=nunit3" "--result=$junit;transform=$xslt"
    local _ex=$?
    
    # we delete the xslt as we don't want to accidentally include it in the artefacts (legal precaution)
    rm -f $xslt

    file_or_die $junit
    echo "Test APP done, exit $_ex"
    return $_ex
}

overall=0
test_app || overall=1

# https://stackoverflow.com/questions/61524738/how-to-fail-gitlab-pipeline-if-there-are-failed-test-in-junit-report
# https://forum.gitlab.com/t/how-to-fail-job-and-pipeline-if-there-are-failed-tests-in-junit-report/37039
exit $overall
