# ornl-watchdog
Application to CHESS-side control of ORNL EDD beamtime: SPEC and CHAP

# Usage
1. Set up some configuration files for CHAP data pprocessing:
   1. detector configurations (start with: `template_yaml/xps23_config.yaml`)
      Define the detector(s) that will be used for the whole experiment -- calibration and strain analysis.
   1. strain analysis configuration (start with: `template_yaml/strain_analysis_config.yaml`)
      Define the material parameters that will be used for strain analysis.
1. Gather and process calibration data using the usual `CHAP` workflow (`template_yaml/calibration_pipeline.yaml`). The crucial product of this step is: a tth calibration configuration yaml file.
1. Set up the configuration file for the watchdog program (template below) and save it to `/nfs/chess/aux/cycles/<cycle>/<station>/<btr>/metadata/watchdog_config.yaml`.
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
   # Uncomment to make copies of updated nexus files to a separate location for viz
   # nsdf_root: /nfs/chess/nsdf01/nsdf/workflow/<btr>

   detectors_yaml: /nfs/chess/aux/cycles/2026-2/id1a3/<btr>/metadata/xps23_config.yaml
   calibration_yaml: /nfs/chess/aux/cycles/2026-2/id1a3/<btr>/reduced_data/tth_calibration_config.yaml
   strain_analysis_yaml: /nfs/chess/aux/cycles/2026-2/id1a3/<btr>/reduced_data/strain_analysis_config.yaml

   datasets: {}
   ```
1. Start the watchdog program. For week 2, use this executable: `/nfs/chess/sw/miniforge3_chap/envs/CHAP_edd-watchdog/bin/edd-watchdog`
   Run `/nfs/chess/sw/miniforge3_chap/envs/CHAP_edd-watchdog/bin/edd-watchdog /nfs/chess/aux/cycles/2026-2/id1a3/<btr>/metadata/watchdog_config.yaml` to start the watchdog

