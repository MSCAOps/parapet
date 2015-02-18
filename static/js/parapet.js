showVerboseData = 0
function toggleVerbose()
{
    console.log("showVerboseData: "+showVerboseData)
    var myObj = document.getElementsByClassName('_verboseData');
    if (showVerboseData > 0) {
        setStyle = "none";
        setSize = "0em";
        setLine = "0em";
        showVerboseData = 0
    }
    else {
        setStyle = "inline";
        setSize = "1em";
        setLine = "1em";
        showVerboseData = 1
    }
    for(var i=0; i<myObj.length; i++)
    {
        myObj[i].style['display'] = setStyle;
        myObj[i].style['font-size'] = setSize;
        myObj[i].style['line-height'] = setLine;
    }
}
