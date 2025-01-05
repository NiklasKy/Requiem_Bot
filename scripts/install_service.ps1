# Run this script as Administrator
$serviceName = "RequiemBotDocker"
$projectPath = "F:\#Communitys\Requiem\Requiem_Bot"  # Adjust this path
$description = "Requiem Bot Docker Service - Manages Docker containers for the Requiem Bot"

# Create a new service
$params = @{
    Name = $serviceName
    BinaryPathName = "docker-compose -f $projectPath\docker-compose.yml up -d"
    DisplayName = "Requiem Bot Docker Service"
    Description = $description
    StartupType = "Automatic"
    DependsOn = "Docker"
}

New-Service @params

# Set recovery options (restart on failure)
$action = New-ScheduledTaskAction -Execute "docker-compose" -Argument "-f $projectPath\docker-compose.yml up -d"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $serviceName -Action $action -Trigger $trigger -Principal $principal -Description $description

Write-Host "Service installed successfully. You can start it with: Start-Service $serviceName" 