#!/bin/sh

test_description='Test "stg pop -keep"'
. ./test-lib.sh
stg init

test_expect_success 'Create a few patches' '
    for i in 0 1 2; do
        stg new p$i -m p$i &&
        echo "patch$i" >> patch$i.txt &&
        stg add patch$i.txt &&
        stg refresh
    done &&
    [ "$(echo $(stg applied))" = "p0 p1 p2" ] &&
    [ "$(echo $(stg unapplied))" = "" ]
'

test_expect_success 'Make some non-conflicting local changes' '
    echo "local" >> patch0.txt
'

test_expect_success 'Pop two patches, keeping local changes' '
    stg pop -n 2 --keep &&
    [ "$(echo $(stg applied))" = "p0" ] &&
    [ "$(echo $(stg unapplied))" = "p1 p2" ] &&
    [ "$(echo $(ls patch?.txt))" = "patch0.txt" ] &&
    [ "$(echo $(cat patch0.txt))" = "patch0 local" ]
'

test_expect_success 'Reset and push patches again' '
    git reset --hard &&
    stg push -a
'

test_expect_success 'Pop a patch without local changes' '
    stg pop --keep &&
    [ "$(echo $(stg applied))" = "p0 p1" ] &&
    [ "$(echo $(stg unapplied))" = "p2" ] &&
    [ "$(echo $(ls patch?.txt))" = "patch0.txt patch1.txt" ]
'

test_done