# Databricks notebook source
# MAGIC %md This solution accelerator notebook is also available at https://github.com/databricks-industry-solutions/hls-patient-risk

# COMMAND ----------

# MAGIC %md
# MAGIC # Patient-Level Risk Scoring Based on Condition History
# MAGIC Longitudinal health records, contain tremendous amount of information with regard to a patients risk factors. For example, using standrad ML techniques, one can investigate the correlation between a patient's health history and a given outcome such as heart attack. In this case, we use a patient’s condition history, durgs taken and demographics information as input, and  use a patinet's encounter's history to identify patients who have been diagnosed with a certain condition (CHF in this example) and train a machine learning model that predicts the risk of an adverse outcome (emergency room admission) within a given timeframe.
# MAGIC 
# MAGIC In this solution accelerator, we assume that the patients data are already stored as in an OMOP 5.3 CDM on Delta Lake and use the OHDSI's patient-level risk prediction methodology to train a classifier that predicts the risk.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Workflow overview
# MAGIC 
# MAGIC In this solution accelerator cover:
# MAGIC 
# MAGIC  1. Ingest simulated clinical data from 100K patients prepared in OMOP 5.3 CMD 
# MAGIC  2. Create cohorts and cohort attributes
# MAGIC  3. Create features based on patinet's history
# MAGIC  4. Train a classifier to preidct outcomes using AutoML
# MAGIC 
# MAGIC [![](https://mermaid.ink/img/pako:eNqVVMFu2zAM_RVCpw1o8wHCEGBYt9OyDut284W2GEetLWUUXawo-u-jrKSL7QTbfJLI90jq6VnPpomOjDWJfg4UGrrx2DL2VQD99sjiG7_HIPAjEZdoHX_B7eb26xLzofPBN9jBDQqeScddZEmXEoAi7OtB6ACh4P50_M6oxUMLTmvDssYnQhmY4E4i0zL9Ss-jJZIzHTafl7T3g8Rz8Y2q1sE3an0SfpoV-xKFID4Sj6JZcLT1gTIfexLiZN_VvM7Cp7wA8T3p4YF9esiBWCvtEcXHAHtiH12OrlarUj4Xvb5erydq25PyBTZJj_givwVBbkmgGfd_A8dBmqjznaLHA7JvdwJxC69QdG5xhxcKn-BUHx7a_4A3MTifxUmXp5kSWL1BsC0OOXaa43K3qYvs6WD_AN-pGS4cY16Y-tgW6CSRkXOnWriPPpydvgyxJOSL6LBWh745XN_bQptDlV4criJ1mJLf6tRZ2gIvOchNpoa3UFMS6HPQXJmeuEfv9Bl5zsTKyI56qozVpZofh04qU4UXhQ57_X_po15gZGOFB7oyqG3unkJz3BfM4SU6BmmkbMprNT5aL78BhKagvg?type=png)](https://mermaid.live/edit#pako:eNqVVMFu2zAM_RVCpw1o8wHCEGBYt9OyDut284W2GEetLWUUXawo-u-jrKSL7QTbfJLI90jq6VnPpomOjDWJfg4UGrrx2DL2VQD99sjiG7_HIPAjEZdoHX_B7eb26xLzofPBN9jBDQqeScddZEmXEoAi7OtB6ACh4P50_M6oxUMLTmvDssYnQhmY4E4i0zL9Ss-jJZIzHTafl7T3g8Rz8Y2q1sE3an0SfpoV-xKFID4Sj6JZcLT1gTIfexLiZN_VvM7Cp7wA8T3p4YF9esiBWCvtEcXHAHtiH12OrlarUj4Xvb5erydq25PyBTZJj_givwVBbkmgGfd_A8dBmqjznaLHA7JvdwJxC69QdG5xhxcKn-BUHx7a_4A3MTifxUmXp5kSWL1BsC0OOXaa43K3qYvs6WD_AN-pGS4cY16Y-tgW6CSRkXOnWriPPpydvgyxJOSL6LBWh745XN_bQptDlV4criJ1mJLf6tRZ2gIvOchNpoa3UFMS6HPQXJmeuEfv9Bl5zsTKyI56qozVpZofh04qU4UXhQ57_X_po15gZGOFB7oyqG3unkJz3BfM4SU6BmmkbMprNT5aL78BhKagvg)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Experiment Design
# MAGIC In this section we outline the terminology used in this solution accelerator, based on on the experiment design outlined in the [Book of OHDSI](https://ohdsi.github.io/TheBookOfOhdsi/PatientLevelPrediction.html#designing-a-patient-level-prediction-study)
# MAGIC 
# MAGIC <img src='https://ohdsi.github.io/TheBookOfOhdsi/images/PatientLevelPrediction/Figure1.png'>
# MAGIC 
# MAGIC |||
# MAGIC |-----|-----|
# MAGIC |Choice|Description|
# MAGIC |Target cohort|How do we define the cohort of persons for whom we wish to predict?|
# MAGIC |Outcome cohort|	How do we define the outcome we want to predict?|
# MAGIC |Time-at-risk|In which time window relative to t=0 do we want to make the prediction?|
# MAGIC |Model	|What algorithms do we want to use, and which potential predictor variables do we include?|
# MAGIC 
# MAGIC #### Washout Period: days (int):
# MAGIC 
# MAGIC > The minimum amount of observation time required before the start of the target cohort. This choice could depend on the available patient time in the training data, but also on the time we expect to be available in the data sources we want to apply the model on in the future. The longer the minimum observation time, the more baseline history time is available for each person to use for feature extraction, but the fewer patients will qualify for analysis. Moreover, there could be clinical reasons to choose a short or longer look-back period. 
# MAGIC 
# MAGIC For our example, we will use a _365-day prior history as look-back period (washout period)_
# MAGIC 
# MAGIC #### Allowed in cohort multiple times? (boolean):
# MAGIC 
# MAGIC >Can patients enter the target cohort multiple times? In the target cohort definition, a person may qualify for the cohort multiple times during different spans of time, for example if they had different episodes of a disease or separate periods of exposure to a medical product. The cohort definition does not necessarily apply a restriction to only let the patients enter once, but in the context of a particular patient-level prediction problem we may want to restrict the cohort to the first qualifying episode. 
# MAGIC 
# MAGIC In our example, _a person can only enter the target cohort once_, i.e. patients who have been diagnosed with CHF most recently. 
# MAGIC 
# MAGIC #### Inlcude if they have experienced the outcome before? (boolean):
# MAGIC 
# MAGIC >Do we allow persons to enter the cohort if they experienced the outcome before? Do we allow persons to enter the target cohort if they experienced the outcome before qualifying for the target cohort? Depending on the particular patient-level prediction problem, there may be a desire to predict incident first occurrence of an outcome, in which case patients who have previously experienced the outcome are not at risk for having a first occurrence and therefore should be excluded from the target cohort. In other circumstances, there may be a desire to predict prevalent episodes, whereby patients with prior outcomes can be included in the analysis and the prior outcome itself can be a predictor of future outcomes. 
# MAGIC 
# MAGIC For our prediction example, we allow all patients who have expereinced the outcome - emergency room visits - to be allowed in the target cohort. 
# MAGIC 
# MAGIC #### time at risk period (start,end), start should be greater or equal than the target cohort start date**:
# MAGIC > How do we define the period in which we will predict our outcome relative to the target cohort start? We have to make two decisions to answer this question. First, does the time-at-risk window start at the date of the start of the target cohort or later? Arguments to make it start later could be that we want to avoid outcomes that were entered late in the record that actually occurred before the start of the target cohort or we want to leave a gap where interventions to prevent the outcome could theoretically be implemented. Second, we need to define the time-at-risk by setting the risk window end, as some specification of days offset relative to the target cohort start or end dates.
# MAGIC 
# MAGIC For our problem we will predict in a time-at-risk window starting 7 days after the start of the target cohort (`min_time_at_risk=7`) up to 365 days later (`max_time_at_risk = 365`)
# MAGIC 
# MAGIC #### Parameter descriptions
# MAGIC |parameter name|description|default value|
# MAGIC |-----|-----|-----|
# MAGIC |`target_condition_concept_id`|qualifying condition to enter the target cohort| 4229440 (CHF)|
# MAGIC |`outcome_concept_id`|outcome to predict| 9203 (Emergency Room Visit)|
# MAGIC |`drug1_concept_id`|concept id for drug exposure history | 40163554 (Warfarin)|
# MAGIC |`drug2_concept_id`|concept id for drug exposure history | 40221901 (Acetaminophen)|
# MAGIC |`cond_history_years`| years of patient history to look up| 5 |
# MAGIC |`max_n_commorbidities`| max number of commorbid conditions to use for the prediction probelm| 5 |
# MAGIC |`min_observation_period`| whashout period in days| 1095 |
# MAGIC |`min_time_at_risk`| days since target cohort start to start the time at risk| 7 |
# MAGIC |`max_time_at_risk`| days since target cohort start to end time at risk window| 365 |

# COMMAND ----------

# MAGIC %md
# MAGIC ## Model Training
# MAGIC To train the classifier we use databricks [AutoML](https://www.databricks.com/product/automl) to train the best model given the training dataset.
# MAGIC In addition to training the best model, AutoML goes one step further by creating [a notebook]($./AtoML-LogisticRegressionClassifier) that includes pre-loaded code with all the necessary steps for training the model. This not only saves time but also ensures consistency in the process. Furthermore, feature importance is included in the code to determine the importance of each feature in the model. This feature importance analysis can provide valuable insights into the factors that influence the model's predictions and can help improve the model's overall performance. With AutoML's advanced capabilities, users can easily create high-performing models while minimizing the time and effort required for training and feature analysis.
# MAGIC 
# MAGIC <img src='https://hls-eng-data-public.s3.amazonaws.com/img/patient_risk_automl.gif'>

# COMMAND ----------

# MAGIC %md
# MAGIC Copyright / License info of the notebook. Copyright Databricks, Inc. [2021].  The source in this notebook is provided subject to the [Databricks License](https://databricks.com/db-license-source).  All included or referenced third party libraries are subject to the licenses set forth below.
# MAGIC 
# MAGIC |Library Name|Library License|Library License URL|Library Source URL| 
# MAGIC | :-: | :-:| :-: | :-:|
# MAGIC |Smolder |Apache-2.0 License| https://github.com/databrickslabs/smolder | https://github.com/databrickslabs/smolder/blob/master/LICENSE|
# MAGIC |Synthea|Apache License 2.0|https://github.com/synthetichealth/synthea/blob/master/LICENSE| https://github.com/synthetichealth/synthea|
# MAGIC | OHDSI/CommonDataModel| Apache License 2.0 | https://github.com/OHDSI/CommonDataModel/blob/master/LICENSE | https://github.com/OHDSI/CommonDataModel |
# MAGIC | OHDSI/ETL-Synthea| Apache License 2.0 | https://github.com/OHDSI/ETL-Synthea/blob/master/LICENSE | https://github.com/OHDSI/ETL-Synthea |
# MAGIC |OHDSI/OMOP-Queries|||https://github.com/OHDSI/OMOP-Queries|
# MAGIC |The Book of OHDSI | Creative Commons Zero v1.0 Universal license.|https://ohdsi.github.io/TheBookOfOhdsi/index.html#license|https://ohdsi.github.io/TheBookOfOhdsi/|
