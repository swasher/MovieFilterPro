$u = [uri]$args[0]
$target = Invoke-RestMethod "http://qnap:8009/api/vault/playback-target/$($u.Host)$($u.Query)"
Start-Process "C:\Program Files\VideoLAN\VLC\vlc.exe" -ArgumentList "`"$($target.unc_path)`""