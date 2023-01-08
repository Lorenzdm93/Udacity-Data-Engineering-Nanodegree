# All imports and installs here
import pandas as pd
import numpy as np
import configparser
from datetime import datetime
import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import udf, col
from pyspark.sql.functions import year, month, dayofmonth, hour, weekofyear, date_format
from pyspark.sql import functions as F
from pyspark.sql import types as T
from pyspark.sql.functions import monotonically_increasing_id, row_number, desc
from pyspark.sql.window import Window
from pyspark.sql.types import IntegerType, TimestampType, StructType, StructField, StringType, DateType, BooleanType, DecimalType, DoubleType

output_bucket = "s3a://udacitycapstone123/" #destination s3 bucket

def configure_spark():
    '''
    this function configures the spark builder 
    and configs the environment to work with aws
    '''
    # Read in the configuration information
    config = configparser.ConfigParser()
    config.read_file(open('creds.cfg'))
    
    # Get the AWS access keys from the configuration file
    KEY = config.get('AWS','KEY')
    SECRET = config.get('AWS','SECRET')

    # Set the AWS access keys as environment variables
    os.environ['AWS_ACCESS_KEY_ID']=KEY
    os.environ['AWS_SECRET_ACCESS_KEY']=SECRET

    # Set up the Spark session
    spark = SparkSession \
            .builder \
            .config("spark.jars.packages", "org.apache.hadoop:hadoop-aws:2.7.0") \
            .config("spark.executor.instances", 10) \
            .config("spark.executor.memory", "8g") \
            .getOrCreate()

def read_csvs(calendar_csv, list_det_csv, list_csv, hoods_csv, reviews_csv):
    '''
    reads the csvs needed for this project
    and return them as pandas dataframes
    '''
    #read local path into variables
    calendar_csv = 'airbnb_data/calendar.csv'
    list_det_csv = 'airbnb_data/listings_detailed.csv'
    list_csv = 'airbnb_data/listings.csv'
    hoods_csv = 'airbnb_data/neighbourhoods.csv'
    reviews_csv = 'airbnb_data/reviews_detailed.csv'
    
    #read csvs into pandas dataframe
    calendar_df = pd.read_csv(calendar_csv)
    list_det_df = pd.read_csv(list_det_csv)
    list_df = pd.read_csv(list_csv)
    hoods_df = pd.read_csv(hoods_csv)
    reviews_df = pd.read_csv(reviews_csv)
    return calendar_df, list_det_df, list_df, hoods_df, reviews_df

def data_cleaning(calendar_df, reviews_df, list_df, list_det_df, hoods_df):
    '''
    performs the data cleaning steps identified
    and needed in the etl notebook
    '''
    # Rename the 'price' column in the calendar dataframe
    calendar_df = calendar_df.rename(columns={'price': 'requested_price'})

    # Drop certain columns from the list_det_df dataframe
    list_det_df = list_det_df.drop(['maximum_nights','minimum_nights','price'], axis=1)

    # Merge the two listing dataframes to create a single dataframe
    listing_df = pd.merge(list_det_df, list_df,  how='left', left_on=['id'], right_on = ['id'])

    # Transpose the dataframe and drop duplicate columns
    listing_df_transposed = listing_df.T
    listing_df_unique = listing_df_transposed.drop_duplicates()

    # Transpose the dataframe back to its original shape
    listing_df = listing_df_unique.T

    # Remove the suffix _x generated by column duplication
    suffix = '_x'
    listing_df = listing_df.rename(columns={col: col.replace(suffix, '') for col in listing_df.columns})

    # Cleaning the Listing by dropping null columns, fillin nas, and replacing 0 to nans where is needed
    listing_df = listing_df.drop('bathrooms',axis=1)
    listing_df = listing_df.fillna('')
    listing_df['price'] = listing_df['price'].replace('$', '')
    null_to_zero = ['bedrooms','beds','review_scores_rating','review_scores_accuracy','review_scores_cleanliness',
                    'review_scores_checkin','reviews_per_month','review_scores_communication','review_scores_location','review_scores_value']
    for i in null_to_zero:
        listing_df[i] = listing_df[i].replace('', 0)

    # Print the number of duplicate rows in each dataframe
    duplicate_listing_id = listing_df[listing_df.duplicated(['id'])]['id'].count()
    print("Number of duplicate listing_ids in listing: ", duplicate_listing_id)

    duplicate_review_id = reviews_df[reviews_df.duplicated(['id'])]['id'].count()
    print("Number of duplicate ids in review: ", duplicate_review_id)

    duplicate_neighbourhood_group = hoods_df[hoods_df.duplicated(['neighbourhood'])]['neighbourhood'].count()
    print("Number of duplicate neighbourhood_group in hoods_df: ", duplicate_neighbourhood_group)

    # Calculate the percentage of missing values in each column of each dataframe
    dfs = [listing_df,calendar_df,reviews_df,hoods_df]
    for df in dfs:
        for col in df.columns:
            pct_missing = np.mean(df[col].isnull())
            print('{} - {}%'.format(col, round(pct_missing*100)))
            
            
def data_types(listing_df):
    '''
    impart the correct data type to the dataframes before writing to S3.
    For listing_df this is done manually, as turns spark dataframe from pandas dataframe,
    for the other I define a spark schema to be passed later
    '''
    #manual conversion for listing_df fields
    listing_df['id'] = listing_df['id'].astype('int32')
    listing_df['listing_url'] = listing_df['listing_url'].astype('str')
    listing_df['scrape_id'] = listing_df['scrape_id'].astype('int32')
    listing_df['last_scraped'] = pd.to_datetime(listing_df['last_scraped'])
    listing_df['source'] = listing_df['source'].astype('str')
    listing_df['name'] = listing_df['name'].astype('str')
    listing_df['description'] = listing_df['description'].astype('str')
    listing_df['neighborhood_overview'] = listing_df['neighborhood_overview'].astype('str')
    listing_df['picture_url'] = listing_df['picture_url'].astype('str')
    listing_df['host_id'] = listing_df['host_id'].astype('int32')
    listing_df['host_url'] = listing_df['host_url'].astype('str')
    listing_df['host_name'] = listing_df['host_name'].astype('str')
    listing_df['host_since'] = pd.to_datetime(listing_df['host_since'])
    listing_df['host_location'] = listing_df['host_location'].astype('str')
    listing_df['host_about'] = listing_df['host_about'].astype('str')
    listing_df['host_response_time'] = listing_df['host_response_time'].astype('str')
    listing_df['host_response_rate'] = listing_df['host_response_rate'].astype('str')
    listing_df['host_acceptance_rate'] = listing_df['host_acceptance_rate'].astype('str')
    listing_df['host_is_superhost'] = listing_df['host_is_superhost'].astype('str')
    listing_df['host_thumbnail_url'] = listing_df['host_thumbnail_url'].astype('str')
    listing_df['host_picture_url'] = listing_df['host_picture_url'].astype('str')
    listing_df['host_neighbourhood'] = listing_df['host_neighbourhood'].astype('str')
    listing_df['host_listings_count'] = listing_df['host_listings_count'].astype('str')
    listing_df['host_total_listings_count'] = listing_df['host_total_listings_count'].astype('str')
    listing_df['host_verifications'] = listing_df['host_verifications'].astype('str')
    listing_df['host_has_profile_pic'] = listing_df['host_has_profile_pic'].astype('str')
    listing_df['host_identity_verified'] = listing_df['host_identity_verified'].astype('str')
    listing_df['neighbourhood'] = listing_df['neighbourhood'].astype('str')
    listing_df['neighbourhood_cleansed'] = listing_df['neighbourhood_cleansed'].astype('str')
    listing_df['neighbourhood_group_cleansed'] = listing_df['neighbourhood_group_cleansed'].astype('str')
    listing_df['latitude'] = listing_df['latitude'].astype('float')
    listing_df['longitude'] = listing_df['longitude'].astype('float')
    listing_df['property_type'] = listing_df['property_type'].astype('str')
    listing_df['room_type'] = listing_df['room_type'].astype('str')
    listing_df['accommodates'] = listing_df['accommodates'].astype('int32')
    listing_df['bathrooms_text'] = listing_df['bathrooms_text'].astype('str')
    listing_df['bedrooms'] = listing_df['bedrooms'].astype('str')
    listing_df['beds'] = listing_df['beds'].astype('int32')
    listing_df['amenities'] = listing_df['amenities'].astype('str')
    listing_df['price'] = listing_df['price'].replace('$', '', regex=True).astype('float', errors='ignore')
    listing_df['minimum_minimum_nights'] = listing_df['minimum_minimum_nights'].astype('int32')
    listing_df['maximum_minimum_nights'] = listing_df['maximum_minimum_nights'].astype('int32')
    listing_df['minimum_maximum_nights'] = listing_df['minimum_maximum_nights'].astype('int32')
    listing_df['maximum_maximum_nights'] = listing_df['maximum_maximum_nights'].astype('int32')
    listing_df['minimum_nights_avg_ntm'] = listing_df['minimum_nights_avg_ntm'].astype('int32')
    listing_df['maximum_nights_avg_ntm'] = listing_df['maximum_nights_avg_ntm'].astype('int32')
    listing_df['has_availability'] = listing_df['has_availability'].astype('str')
    listing_df['availability_30'] = listing_df['availability_30'].astype('int32')
    listing_df['availability_60'] = listing_df['availability_60'].astype('int32')
    listing_df['availability_90'] = listing_df['availability_90'].astype('int32')
    listing_df['availability_365'] = listing_df['availability_365'].astype('int32')
    listing_df['number_of_reviews'] = listing_df['number_of_reviews'].astype('int32')
    listing_df['number_of_reviews_ltm'] = listing_df['number_of_reviews_ltm'].astype('int32')
    listing_df['number_of_reviews_l30d'] = listing_df['number_of_reviews_l30d'].astype('int32')
    listing_df['first_review'] = pd.to_datetime(listing_df['first_review'])
    listing_df['last_review'] = pd.to_datetime(listing_df['last_review'])
    listing_df['review_scores_rating'] = listing_df['review_scores_rating'].astype('int32')
    listing_df['review_scores_accuracy'] = listing_df['review_scores_accuracy'].astype('int32')
    listing_df['review_scores_cleanliness'] = listing_df['review_scores_cleanliness'].astype('int32')
    listing_df['review_scores_checkin'] = listing_df['review_scores_checkin'].astype('int32')
    listing_df['review_scores_communication'] = listing_df['review_scores_communication'].astype('int32')
    listing_df['review_scores_location'] = listing_df['review_scores_location'].astype('int32')
    listing_df['review_scores_value'] = listing_df['review_scores_value'].astype('int32')
    listing_df['license'] = listing_df['license'].astype('str')
    listing_df['instant_bookable'] = listing_df['instant_bookable'].astype('str')
    listing_df['calculated_host_listings_count'] = listing_df['calculated_host_listings_count'].astype('str')
    listing_df['calculated_host_listings_count_entire_homes'] = listing_df['calculated_host_listings_count_entire_homes'].astype('str')
    listing_df['calculated_host_listings_count_private_rooms'] = listing_df['calculated_host_listings_count_private_rooms'].astype('str')
    listing_df['calculated_host_listings_count_shared_rooms'] = listing_df['calculated_host_listings_count_shared_rooms'].astype('str')
    listing_df['reviews_per_month'] = listing_df['reviews_per_month'].astype('float')
    
    #creating schemas for the others
    calendar_schema = StructType([
        StructField('listing_id', StringType(), True),
        StructField('date', TimestampType(), True),
        StructField('available', BooleanType(), True),
        StructField('requested_price', DecimalType(), True),
        StructField('adjusted_price', DecimalType(), True)
    ])

    hoods_schema = StructType([
            StructField('neighbourhood_group', StringType()),
            StructField('neighbourhood', StringType())
        ])

    reviews_schema = StructType([
            StructField('listing_id', IntegerType()),
            StructField('id', IntegerType()),
            StructField('date', TimestampType()),
            StructField('reviewer_id', IntegerType()),
            StructField('reviewer_name', StringType()),
            StructField('comments', StringType())
        ])
    

def pre_processing_s3():
    '''
    function that created the spark dataframes,
    prepares them to write to s3 and uploads to s3
    '''
    #define spark dataframes
    df_hoods = spark.read.csv(hoods_csv, header=True, sep=",", schema=hoods_schema)
    df_reviews = spark.read.csv(reviews_csv, header=True, sep=",", schema=reviews_schema)
    df_reviews = df_reviews.withColumnRenamed("id", "review_id").withColumnRenamed("date", "review_date")
    df_listing = spark.createDataFrame(listing_df)
    df_calendar = spark.read.format('csv').option('header', 'true').option('inferSchema', 'true').option('sep', ',').load(calendar_csv)
    df_calendar = df_calendar.drop('price')
    
    #preparing the various "tables" before uploading to the S3 as parquet
    # REVIEW TABLE - extract columns to create review table
    df_reviews = df_reviews.na.drop()
    df_reviews = df_reviews.withColumn('month', month('review_date'))
    reviews_table = df_reviews.select('listing_id', 'review_id', 'review_date', 'reviewer_id', 'reviewer_name', 'comments', 'month')

    #NEIGHBOURHOODS - extract columns to create Hoods table
    hoods_table = df_hoods.select('neighbourhood_group', 'neighbourhood')

    #CALENDAR - extract columns to create CALENDAR table
    df_calendar = df_calendar.withColumn('month', month('date'))
    calendar_table = df_calendar.select('listing_id', 'month', 'date', 'available', 'adjusted_price', 'minimum_nights', 'maximum_nights')

    #LISTING - extract columns to create LISTING table
    df_listing = df_listing.withColumn('month', month('host_since'))
    #including only some columns in the listing table for demostration purposes and because it is very slow
    listing_table = df_listing.select('id', 'month','name','description','host_id','host_name','host_since','source','latitude','longitude','price','review_scores_rating','reviews_per_month','room_type')
    
    ##Creating the fact table BOOKINGS now
    df_bookings_stg = df_calendar.join(listing_table, on=[df_calendar.listing_id == listing_table.id], how='left')
    df_bookings = df_bookings_stg.join(df_reviews, on=[df_bookings_stg.listing_id == df_reviews.listing_id], how='left')

    #preparing BOOKINGS before uploading to the S3 as parquet
    # extract columns to create review table
    df_bookings = df_bookings.withColumn('month_review', month('review_date'))
    #including only some columns in the listing table for demostration purposes and because it is very slow
    booking_table=df_bookings.select('id','month_review','name','description','host_id','host_name','host_since','source','latitude',
                                      'longitude','adjusted_price','review_id','review_date','reviewer_id','review_scores_rating',
                                      'reviews_per_month','room_type')
    print('Data is ready to be uploaded to S3!')
    
def write_to_s3():
    '''
    function to write spark dataframe to s3 as parquet files
    '''
    # WRITING TABLES AS PARQUET TO S3
    # write REVIEW table to parquet files partitioned by month 
    reviews_table.write.mode('overwrite').partitionBy('month').parquet(output_bucket + 'reviews')
    print('Review Table is created in the S3 bucket!')

    # write HOODS table to parquet files partitioned by neighbourhood_group
    hoods_table.write.mode('overwrite').partitionBy('neighbourhood_group').parquet(output_bucket + 'neighbourhoods')
    print('Neighbourhoods Table is created in the S3 bucket!')

    # write CALENDAR table to parquet files partitioned by month
    calendar_table.write.mode('overwrite').partitionBy('month').parquet(output_bucket + 'calendar')
    print('Calendar Table is created in the S3 bucket!')

    # write LISTING table to parquet files partitioned by month and room type
    listing_table.write.mode('overwrite').partitionBy('month', 'room_type').parquet(output_bucket + 'listing')
    print('Listing Table is created in the S3 bucket!')

    # write BOOKINGS (fact) table to parquet files partitioned month
    booking_table.write.mode('overwrite').partitionBy('month_review').parquet(output_bucket + 'booking') 
    print('Booking Table is created in the S3 bucket!')


def data_quality():
    '''
    reads from s3 the parquet files uploaded before.
    runs a check to see if the num of rows coincides pre and post upload
    '''
    #reading the tables from the S3 in order to parse, run analysis etc
    listing = spark.read.parquet(output_bucket + 'listing')
    calendar = spark.read.parquet(output_bucket + 'calendar')
    neighbourhoods = spark.read.parquet(output_bucket + 'neighbourhoods')
    reviews = spark.read.parquet(output_bucket + 'reviews')
    booking = spark.read.parquet(output_bucket + 'booking')
    
    # Get the count of rows in the dataframe
    uploaded_table = ['booking_table','listing_table','reviews_table','hoods_table','calendar_table']
    downloaded_tables = ['booking','listing','reviews','neighbourhoods','calendar']

    expected_count = []
    row_count = []

    for i in uploaded_table:
        expected_count.append(i)

    for i in downloaded_tables:
        row_count.append(i)

    # Compare the counts
    for uploaded, downloaded in zip(uploaded_table, downloaded_tables):
    if downloaded.count() != uploaded.count():
        raise ValueError("Data is incomplete. Expected {} rows in {} but found {}".format(uploaded.count(), uploaded, downloaded.count()))
            
def main():
    spark = configure_spark()
    
    read_csvs(calendar_csv, list_det_csv, list_csv, hoods_csv, reviews_csv) 
    data_cleaning(calendar_df, reviews_df, list_df, list_det_df, hoods_df)
    data_types(listing_df)
    pre_processing_s3()
    write_to_s3()
    data_quality()

if __name__ == "__main__":
    main()
