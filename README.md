# ornl-watchdog
Application to CHESS-side control of ORNL EDD beamtime: SPEC and CHAP

# Usage
1. First, gather and process calibration scans and process using the usual `CHAP`. Three CHAP configuraiton files will be needed before starting the watchdog program:
   1. detector id / shape configuration
      ```yaml
      detectors:
      - id: 0
	    shape: [4096,]
    	attrs:
	      eta: 180
      - id: 22
        shape: [4096,]
     	attrs:
	      eta: 0
      ```
   1. calibration cofiguration (output by CHAP calibration workflow)
   1. strain analysis configuration (output by CHAP strain analysis workflow)
1. Next, set up the configuration file for the watchdog program (template below) and save it to `/nfs/chess/aux/cycles/<cycle>/<station>/<btr>/metadata/watchdog_config.yaml`.
   ```yaml
   filename: /nfs/chess/aux/cycles/2026-2/id1a3/<btr>/metadata/watchdog_config.yaml

   spec_host: id1a3.classe.cornell.edu
   spec_port: 6510
   spec_timeout: 30

   labx_motor: <labx>
   labz_motor: <labz>
   tseries_npts: 1
   tseries_exposure: 10

   watch_root: /nfs/chess/aux/cycles/2026-2/id1a3/<btr>/metadata/autonomous-edd/
   analysis_root: /nfs/chess/aux/cycles/2026-2/id1a3/<btr>/reduced_data/

   detectors_yaml: /nfs/chess/aux/cycles/2026-2/id1a3/<btr>/metadata/xps23_config.yaml
   calibration_yaml: /nfs/chess/aux/cycles/2026-2/id1a3/<btr>/reduced_data/tth_calibration_config.yaml
   strain_analysis_yaml: /nfs/chess/aux/cycles/2026-2/id1a3/<btr>/reduced_data/strain_analysis_config.yaml

   datasets: {}
   ```
1. Finally, start the watchdog program. For week 2, use this executable: `/nfs/chess/user/kls286/demo/miniforge3/envs/CHAP_edd/bin/edd-watchdog`
   Run `/nfs/chess/user/kls286/demo/miniforge3/envs/CHAP_edd/bin/edd-watchdog /nfs/chess/aux/cycles/2026-2/id1a3/<btr>/metadata/watchdog_config.yaml` to start the watchdog

